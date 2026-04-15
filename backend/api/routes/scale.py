"""PATCH /jobs/{id}/scale — user override of scale factor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_job_service, get_result_store
from backend.services.job_service import JobService
from backend.storage.result_store import ResultStore

router = APIRouter(prefix="/jobs", tags=["scale"])


class ScaleOverrideBody(BaseModel):
    meters_per_pixel: float
    source: str = "user"


@router.patch("/{job_id}/scale")
async def patch_scale(
    job_id: str,
    body: ScaleOverrideBody,
    job_svc: JobService = Depends(get_job_service),
    results: ResultStore = Depends(get_result_store),
) -> dict:
    if not job_svc.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    base = results.get(job_id) or {}
    scale = {
        "meters_per_pixel": body.meters_per_pixel,
        "source": body.source,
        "confidence": 1.0,
    }
    out = {**base, "scale": scale}
    results.put(job_id, out)
    return {"job_id": job_id, "scale": scale}
