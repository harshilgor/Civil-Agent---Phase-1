"""Channel A — Structured form input endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException

from src.core.graph_builder import GraphBuilder
from src.schema.input_models import (
    BuildingGraphResponse,
    GridModificationRequest,
    StructuredInputRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory store — will be replaced by a proper DB in production
_store: dict[str, BuildingGraphResponse] = {}
_builder = GraphBuilder()


@router.post("/structured", response_model=BuildingGraphResponse, status_code=201)
async def create_building_from_structured_input(
    request: StructuredInputRequest,
) -> BuildingGraphResponse:
    """Build a Building Graph from structured parameters.

    Validates input, generates grid, stories, walls, facade, columns, and
    cores, then returns the complete Building Graph.
    """
    try:
        graph = _builder.from_structured_input(request)
    except Exception as exc:
        logger.error("structured_input_failed", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project_id = str(uuid.uuid4())
    now = datetime.utcnow()
    response = BuildingGraphResponse(
        project_id=project_id,
        created_at=now,
        updated_at=now,
        building_graph=graph,
    )
    _store[project_id] = response
    logger.info("building_created", project_id=project_id)
    return response


@router.get("/{project_id}", response_model=BuildingGraphResponse)
async def get_building(project_id: str) -> BuildingGraphResponse:
    """Retrieve a previously created Building Graph."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return _store[project_id]


@router.put("/{project_id}/grid", response_model=BuildingGraphResponse)
async def update_grid(
    project_id: str,
    modification: GridModificationRequest,
) -> BuildingGraphResponse:
    """Modify the grid of an existing Building Graph and recompute affected fields."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    existing = _store[project_id]
    bg = existing.building_graph

    # Rebuild grid with modified parameters
    length_mm = bg.grid.x_lines[-1].position_mm - bg.grid.x_lines[0].position_mm
    width_mm = bg.grid.y_lines[-1].position_mm - bg.grid.y_lines[0].position_mm

    new_grid = _builder.grid_generator.generate(
        length_mm=length_mm,
        width_mm=width_mm,
        preferred_bay_x_mm=modification.preferred_bay_x_mm or 8000,
        preferred_bay_y_mm=modification.preferred_bay_y_mm or 8000,
        min_bay_mm=modification.min_bay_mm or 4000,
        max_bay_mm=modification.max_bay_mm or 15000,
        x_constraints=modification.x_constraints or [],
        y_constraints=modification.y_constraints or [],
    )

    # Recompute column candidates
    new_columns = _builder.zone_classifier.identify_columns(new_grid)

    # Create updated graph (immutable: new instance)
    updated_bg = bg.model_copy(
        update={
            "grid": new_grid,
            "column_candidates": new_columns,
        }
    )

    now = datetime.utcnow()
    updated_response = BuildingGraphResponse(
        project_id=project_id,
        created_at=existing.created_at,
        updated_at=now,
        building_graph=updated_bg,
    )
    _store[project_id] = updated_response
    logger.info("grid_updated", project_id=project_id)
    return updated_response


@router.delete("/{project_id}", status_code=204)
async def delete_building(project_id: str) -> None:
    """Delete a stored Building Graph."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    del _store[project_id]
    logger.info("building_deleted", project_id=project_id)
