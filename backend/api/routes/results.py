"""GET /jobs/{id}/results — rooms, boundaries, scale, metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.api.deps import get_image_store, get_job_service, get_result_store
from backend.services.job_service import JobService
from backend.storage.image_store import ImageStore
from backend.storage.job_store import JobStatus
from backend.storage.result_store import ResultStore

router = APIRouter(prefix="/jobs", tags=["results"])


@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
    results: ResultStore = Depends(get_result_store),
) -> dict:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    if rec.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job not completed: {rec.status.value}")
    payload = results.get(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Results not found")
    return payload


@router.get("/{job_id}/image")
async def get_source_image(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
    images: ImageStore = Depends(get_image_store),
) -> FileResponse:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    path = images.path_for(job_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Source image not found")
    return FileResponse(path)
