"""Channel B — CAD file upload endpoints (DXF / DWG / IFC).

Contract mirrors Channel C: ``POST /cad`` persists the upload, registers
an async job, and submits a Celery task; ``GET /cad/{job_id}/status``
(and the unified ``GET /api/v1/jobs/{job_id}``) resolve via the shared
async job store.

In Step 5 the worker returns a *synthetic* graph — the real DXF / DWG /
IFC parsers land in Steps 7-8 and slot in behind the same task name.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.api import async_job_store
from src.config import settings
from src.schema.building_graph import BuildingGraph
from src.schema.input_models import CADUploadResponse, JobStatusResponse

logger = structlog.get_logger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".dxf", ".dwg", ".ifc"}


@router.post("/cad", response_model=CADUploadResponse, status_code=202)
async def upload_cad_file(file: UploadFile = File(...)) -> CADUploadResponse:
    """Upload a CAD/BIM file (.dxf / .dwg / .ifc) for processing."""

    filename = file.filename or "unknown"
    ext = _get_extension(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    file_type = ext.lstrip(".").upper()
    job_id = uuid.uuid4().hex

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{job_id}{ext}"
    dest.write_bytes(await file.read())

    async_job_store.register(
        job_id,
        channel="cad",
        filename=filename,
        file_type=file_type,
        source_path=str(dest),
    )

    _enqueue_cad_task(job_id, str(dest), file_type=file_type, filename=filename)

    record = async_job_store.get(job_id)
    status = record.status if record else "queued"
    return CADUploadResponse(
        job_id=job_id,
        status=status,
        filename=filename,
        file_type=file_type,
    )


@router.get("/cad/{job_id}/status", response_model=JobStatusResponse)
async def cad_job_status(job_id: str) -> JobStatusResponse:
    """Poll the status of a CAD processing job."""

    record = async_job_store.refresh(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _record_to_response(record)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enqueue_cad_task(
    job_id: str, dest: str, *, file_type: str, filename: str
) -> None:
    try:
        from src.worker.tasks import process_cad_file
    except Exception as exc:  # pragma: no cover
        logger.warning("celery_import_failed", error=str(exc))
        process_cad_file = None  # type: ignore[assignment]

    if process_cad_file is None:
        _run_inprocess_stub(job_id, dest, file_type)
        return

    try:
        async_result = process_cad_file.delay(job_id, dest, file_type)
    except Exception as exc:  # pragma: no cover — broker unreachable
        logger.warning(
            "celery_enqueue_failed",
            job_id=job_id,
            filename=filename,
            error=str(exc),
        )
        _run_inprocess_stub(job_id, dest, file_type)
        return

    async_job_store.attach_celery_task(job_id, async_result.id)
    async_job_store.reconcile_from_async_result(job_id, async_result)
    logger.info(
        "cad_upload_queued",
        job_id=job_id,
        celery_task_id=async_result.id,
        filename=filename,
        file_type=file_type,
    )


def _run_inprocess_stub(job_id: str, dest: str, file_type: str) -> None:
    """Run the real CAD pipeline in-process when Celery is unreachable.

    The function name is a historical artefact from Step 5 when every
    Channel-B payload was synthetic; Step 6 flipped this to the real
    parser + graph builder so the endpoint doesn't quietly return stub
    data when a broker outage forces the sync path.  A parse failure
    surfaces as a ``failed`` job record with a structured error message.
    """

    from src.worker.tasks import DWGUnsupportedError, run_cad_inprocess

    try:
        payload = run_cad_inprocess(job_id, dest, file_type)
    except DWGUnsupportedError as exc:
        async_job_store.mark_failed(
            job_id, f"DWG parsing unavailable: {exc}"
        )
        return
    except Exception as exc:
        logger.error(
            "cad_inprocess_parse_failed",
            job_id=job_id,
            file_type=file_type,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        async_job_store.mark_failed(
            job_id, f"{type(exc).__name__}: {exc}"
        )
        return
    graph = BuildingGraph.model_validate(payload["building_graph"])
    async_job_store.mark_completed(job_id, graph)


def _record_to_response(record: async_job_store.AsyncJobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        progress_percent=record.progress_percent,
        result_id=record.job_id if record.status == "completed" else None,
        error=record.error,
        building_graph=record.building_graph,
    )


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
