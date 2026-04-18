"""Channel C — Floor-plan image upload endpoints.

Processing is queued as an async Celery job (Gap 7). Clients poll
``GET /image/{job_id}/status`` to learn when the building graph is ready.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.config import settings
from src.schema.input_models import ImageUploadResponse, JobStatusResponse

logger = structlog.get_logger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".tif", ".bmp"}
_jobs: dict[str, dict] = {}


@router.post("/image", response_model=ImageUploadResponse, status_code=202)
async def upload_floor_plan_image(file: UploadFile = File(...)) -> ImageUploadResponse:
    """Upload a floor-plan image for CV pipeline processing."""
    filename = file.filename or "unknown"
    ext = _get_extension(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    job_id = str(uuid.uuid4())
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{job_id}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    _jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "result_id": None,
        "error": None,
        "image_path": str(dest),
        "celery_task_id": None,
    }

    # Enqueue the Celery task when the worker stack is available
    try:
        from src.worker.tasks import process_floor_plan

        async_result = process_floor_plan.delay(job_id, str(dest))
        _jobs[job_id]["status"] = "processing"
        _jobs[job_id]["celery_task_id"] = async_result.id
        logger.info(
            "image_upload_queued",
            job_id=job_id,
            celery_task_id=async_result.id,
            filename=filename,
        )
    except Exception as exc:  # pragma: no cover — no broker in unit tests
        _jobs[job_id]["status"] = "queued"
        logger.warning("celery_enqueue_failed", job_id=job_id, error=str(exc))

    return ImageUploadResponse(
        job_id=job_id,
        status=_jobs[job_id]["status"],
        filename=filename,
    )


@router.get("/image/{job_id}/status", response_model=JobStatusResponse)
async def image_job_status(job_id: str) -> JobStatusResponse:
    """Poll the status of an image processing job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    j = _jobs[job_id]

    # If a Celery task was submitted, check its live status
    celery_task_id = j.get("celery_task_id")
    if celery_task_id:
        try:
            from src.worker.celery_app import celery_app

            if celery_app is not None:
                ar = celery_app.AsyncResult(celery_task_id)
                j["status"] = ar.state.lower() if ar.state else j["status"]
                if ar.successful():
                    j["status"] = "completed"
                    j["progress"] = 100
                    j["result_id"] = job_id
                elif ar.failed():
                    j["status"] = "failed"
                    j["error"] = str(ar.info) if ar.info else "Unknown error"
        except Exception as exc:  # pragma: no cover
            logger.warning("celery_status_check_failed", error=str(exc))

    return JobStatusResponse(
        job_id=job_id,
        status=j["status"],
        progress_percent=j["progress"],
        result_id=j["result_id"],
        error=j["error"],
    )


def _get_extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
