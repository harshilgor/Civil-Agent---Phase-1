"""Channel B — CAD file upload endpoints (DXF / DWG / IFC).

Processing is queued as an async job.  Full implementation in Steps 4-5.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File

from src.schema.input_models import CADUploadResponse, JobStatusResponse

logger = structlog.get_logger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".dxf", ".dwg", ".ifc"}
_jobs: dict[str, dict] = {}


@router.post("/cad", response_model=CADUploadResponse, status_code=202)
async def upload_cad_file(file: UploadFile = File(...)) -> CADUploadResponse:
    """Upload a CAD/BIM file for processing.

    Accepted formats: .dxf, .dwg, .ifc
    """
    filename = file.filename or "unknown"
    ext = _get_extension(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "progress": 0, "result_id": None, "error": None}

    logger.info("cad_upload_received", job_id=job_id, filename=filename, ext=ext)

    # TODO: save file to disk and queue Celery task (Steps 4-5)

    return CADUploadResponse(
        job_id=job_id,
        status="processing",
        filename=filename,
        file_type=ext.lstrip(".").upper(),
    )


@router.get("/cad/{job_id}/status", response_model=JobStatusResponse)
async def cad_job_status(job_id: str) -> JobStatusResponse:
    """Poll the status of a CAD processing job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    j = _jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=j["status"],
        progress_percent=j["progress"],
        result_id=j["result_id"],
        error=j["error"],
    )


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
