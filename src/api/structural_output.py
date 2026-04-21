"""Phase 2 Structural Design Graph endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.api.structured_input import _store
from src.structural.engine import StructuralEngine

logger = structlog.get_logger(__name__)

router = APIRouter()

_engine = StructuralEngine()
_structural_store: dict[str, dict] = {}


@router.post("/{project_id}/structural")
async def build_structural_graph(project_id: str) -> JSONResponse:
    """Run the Phase 2 engine on an existing Building Graph."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    bg = _store[project_id].building_graph
    try:
        sdg = _engine.build(bg, graph_id=project_id)
    except Exception as exc:
        logger.error("structural_engine_failed", project_id=project_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    payload = sdg.model_dump(mode="json")
    _structural_store[project_id] = payload
    logger.info(
        "structural_graph_built",
        project_id=project_id,
        zone_count=len(sdg.zones),
        support_count=len(sdg.support_candidates),
        constraint_count=len(sdg.constraints),
    )
    return JSONResponse(content=payload, status_code=201)


@router.get("/{project_id}/structural")
async def get_structural_graph(project_id: str) -> JSONResponse:
    """Retrieve a previously built Structural Design Graph."""
    if project_id not in _structural_store:
        raise HTTPException(
            status_code=404,
            detail=f"Structural graph for {project_id} not found — POST first.",
        )
    return JSONResponse(content=_structural_store[project_id])


@router.get("/{project_id}/structural/summary")
async def get_structural_summary(project_id: str) -> JSONResponse:
    """Return a compact summary of the structural design graph."""
    if project_id not in _structural_store:
        raise HTTPException(status_code=404, detail=f"Structural graph for {project_id} not found")

    sdg = _structural_store[project_id]
    summary = {
        "zone_count": len(sdg.get("zones", [])),
        "support_candidate_count": len(sdg.get("support_candidates", [])),
        "forbidden_region_count": len(sdg.get("forbidden_regions", [])),
        "vertical_alignment_group_count": len(sdg.get("vertical_alignment_groups", [])),
        "gravity_system_candidates": [
            {"type": g["system_type"], "plausibility": g["plausibility"]}
            for g in sdg.get("gravity_system_candidates", [])
        ],
        "lateral_system_candidates": [
            {"type": l["system_type"], "plausibility": l["plausibility"]}
            for l in sdg.get("lateral_system_candidates", [])
        ],
        "constraint_count": len(sdg.get("constraints", [])),
        "metadata": sdg.get("metadata", {}),
    }
    return JSONResponse(content=summary)
