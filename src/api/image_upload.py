"""Channel C — Floor-plan image upload endpoints.

The endpoint persists the image to :data:`settings.upload_dir`, registers
an async job in :mod:`src.api.async_job_store`, and submits a Celery
task.  The contract is:

* ``POST /image``               → ``202 Accepted`` + ``{job_id, status}``
* ``GET /image/{job_id}/status`` → same status a client would get from
  the unified ``GET /api/v1/jobs/{job_id}`` endpoint; kept for
  backward-compat with existing frontend code paths.

When Celery isn't importable (unit tests without the worker extra, or a
fresh checkout where the broker isn't running), the endpoint falls back
to an in-process stub so the upload contract still works end-to-end.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.api import async_job_store
from src.config import settings
from src.schema.building_graph import BuildingGraph
from src.schema.input_models import ImageUploadResponse, JobStatusResponse

logger = structlog.get_logger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".tif", ".bmp"}


@router.post("/image", response_model=ImageUploadResponse, status_code=202)
async def upload_floor_plan_image(file: UploadFile = File(...)) -> ImageUploadResponse:
    """Upload a floor-plan image for CV pipeline processing."""

    filename = file.filename or "unknown"
    ext = _get_extension(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    job_id = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{job_id}{ext}"
    dest.write_bytes(await file.read())

    async_job_store.register(
        job_id,
        channel="image",
        filename=filename,
        file_type=ext.lstrip(".").upper(),
        source_path=str(dest),
    )

    _enqueue_image_task(job_id, str(dest), filename=filename)

    record = async_job_store.get(job_id)
    status = record.status if record else "queued"
    return ImageUploadResponse(job_id=job_id, status=status, filename=filename)


@router.get("/image/{job_id}/status", response_model=JobStatusResponse)
async def image_job_status(job_id: str) -> JobStatusResponse:
    """Poll the status of an image processing job.

    Delegates to :mod:`src.api.async_job_store` so this endpoint and the
    unified ``GET /api/v1/jobs/{job_id}`` agree byte-for-byte.
    """

    record = async_job_store.refresh(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _record_to_response(record)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enqueue_image_task(job_id: str, dest: str, *, filename: str) -> None:
    """Submit the Celery task, or fall back to the in-process stub."""

    try:
        from src.worker.tasks import process_floor_plan
    except Exception as exc:  # pragma: no cover
        logger.warning("celery_import_failed", error=str(exc))
        process_floor_plan = None  # type: ignore[assignment]

    if process_floor_plan is None:
        _run_inprocess_stub(job_id, dest)
        return

    try:
        async_result = process_floor_plan.delay(job_id, dest)
    except Exception as exc:  # pragma: no cover — broker unreachable
        logger.warning(
            "celery_enqueue_failed",
            job_id=job_id,
            filename=filename,
            error=str(exc),
        )
        _run_inprocess_stub(job_id, dest)
        return

    async_job_store.attach_celery_task(job_id, async_result.id)
    # Eager mode finishes synchronously; reconcile against the live
    # AsyncResult so a subsequent GET sees ``completed`` without hitting
    # the result backend (which is unavailable in tests).
    async_job_store.reconcile_from_async_result(job_id, async_result)
    logger.info(
        "image_upload_queued",
        job_id=job_id,
        celery_task_id=async_result.id,
        filename=filename,
    )


def _run_inprocess_stub(job_id: str, dest: str) -> None:
    """Final fallback: run the synthetic stub in the request process."""

    from src.worker.tasks import run_floor_plan_stub

    try:
        payload = run_floor_plan_stub(job_id, dest)
    except Exception as exc:  # pragma: no cover
        async_job_store.mark_failed(job_id, f"stub failed: {exc}")
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
