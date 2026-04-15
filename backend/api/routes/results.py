"""GET /jobs/{id}/results — rooms, boundaries, scale, metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_job_service, get_result_store
from backend.services.job_service import JobService
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
