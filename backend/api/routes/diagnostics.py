"""GET /jobs/{id}/diagnostics — agreement maps, decision log (Deep mode)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_job_service, get_result_store
from backend.services.job_service import JobService
from backend.storage.result_store import ResultStore

router = APIRouter(prefix="/jobs", tags=["diagnostics"])


@router.get("/{job_id}/diagnostics")
async def get_diagnostics(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
    results: ResultStore = Depends(get_result_store),
) -> dict:
    if not job_svc.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    payload = results.get(job_id) or {}
    diag = payload.get("metadata", {}).get("diagnostics", {})
    return {"job_id": job_id, "diagnostics": diag or {}}
