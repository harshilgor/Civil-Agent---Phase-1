"""GET /jobs/{id} — status, progress %, current stage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_job_service
from backend.services.job_service import JobService
from backend.storage.job_store import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(job_id: str, job_svc: JobService = Depends(get_job_service)) -> dict:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": rec.id,
        "status": rec.status.value,
        "progress_pct": rec.progress_pct,
        "current_stage": rec.current_stage,
        "error_message": rec.error_message,
        "meta": rec.meta,
    }


@router.get("/{job_id}/running")
async def job_is_running(job_id: str, job_svc: JobService = Depends(get_job_service)) -> dict[str, bool]:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"running": rec.status == JobStatus.RUNNING}
