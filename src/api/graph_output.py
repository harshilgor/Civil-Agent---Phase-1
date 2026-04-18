"""Building Graph retrieval and export endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.api.structured_input import _store

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/{project_id}/export")
async def export_building_graph(
    project_id: str,
    format: str = Query(default="json", pattern="^(json|geojson|csv)$"),
) -> JSONResponse:
    """Export a Building Graph in the requested format.

    Supported formats:
    - ``json``    — full Building Graph JSON
    - ``geojson`` — GeoJSON representation (not yet implemented)
    - ``csv``     — tabular export (not yet implemented)
    """
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    bg = _store[project_id].building_graph

    if format == "json":
        return JSONResponse(content=bg.model_dump(mode="json"))

    if format == "geojson":
        raise HTTPException(status_code=501, detail="GeoJSON export not yet implemented")

    if format == "csv":
        raise HTTPException(status_code=501, detail="CSV export not yet implemented")

    raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
