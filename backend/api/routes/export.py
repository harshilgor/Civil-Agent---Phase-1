"""GET /jobs/{id}/export?format=geojson|json|csv"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from backend.api.deps import get_export_service, get_job_service, get_result_store
from backend.services.export_service import ExportService
from backend.services.job_service import JobService
from backend.storage.job_store import JobStatus
from backend.storage.result_store import ResultStore

router = APIRouter(prefix="/jobs", tags=["export"])


@router.get("/{job_id}/export")
async def export_results(
    job_id: str,
    export_format: Literal["json", "geojson", "csv"] = Query("json", alias="format"),
    job_svc: JobService = Depends(get_job_service),
    results: ResultStore = Depends(get_result_store),
    exporter: ExportService = Depends(get_export_service),
) -> Response:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    if rec.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job not completed")
    payload = results.get(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Results not found")
    try:
        content_type, body = exporter.export(payload, export_format)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    if content_type == "text/csv":
        return PlainTextResponse(body, media_type=content_type)
    return Response(content=body, media_type=content_type)
