"""Channel A — Structured form input endpoints.

Every graph produced here has:

* a stable ``project_id`` (UUID4 hex) used by the frontend as the primary
  handle for subsequent GET / PUT / DELETE / export calls;
* a ``job_id`` stamped on ``BuildingMetadata.job_id`` (and used as the
  provenance ``run_id`` on every element) so the Channel-A synchronous
  flow lines up with the Channel-B / C asynchronous flow — the same
  ``GET /api/v1/jobs/{job_id}`` endpoint resolves either one;
* per-element :class:`~src.schema.provenance.ProvenanceRecord` stamps
  (``detector_source=STRUCTURED_FORM``) on every wall, room, column, and
  core;
* a structured :class:`~src.schema.assumptions.AssumptionRecord` list on
  ``BuildingMetadata.assumption_register`` — the review UI / Phase 3
  optimiser read these to drive the override flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException

from src.core.assumption_builder import apply_override
from src.core.graph_builder import GraphBuilder
from src.core.provenance_helpers import structured_form_provenance
from src.schema.input_models import (
    AssumptionOverrideRequest,
    BuildingGraphResponse,
    GridModificationRequest,
    StructuredInputRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# --------------------------------------------------------------------------
# In-process store.
#
# ``_store``         : project_id -> BuildingGraphResponse
# ``_job_index``     : job_id     -> project_id
#
# This is the Phase-1 MVP backing store; the DB-backed replacement is
# scheduled for Step 10.  Both dicts are module-level singletons so the
# jobs router (``src/api/jobs.py``) can share them without circular import
# shenanigans.
# --------------------------------------------------------------------------
_store: dict[str, BuildingGraphResponse] = {}
_job_index: dict[str, str] = {}
_builder = GraphBuilder()


def _register(project_id: str, job_id: str, response: BuildingGraphResponse) -> None:
    _store[project_id] = response
    _job_index[job_id] = project_id


def _lookup_by_job(job_id: str) -> Optional[BuildingGraphResponse]:
    project_id = _job_index.get(job_id)
    if project_id is None:
        return None
    return _store.get(project_id)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("/structured", response_model=BuildingGraphResponse, status_code=201)
async def create_building_from_structured_input(
    request: StructuredInputRequest,
) -> BuildingGraphResponse:
    """Build a Building Graph from structured parameters.

    Synchronous: the Channel-A pipeline has no ML inference to wait on, so
    the graph is returned in the same response.  ``job_id`` is still issued
    so the frontend can resolve this project through the unified jobs
    endpoint alongside Channels B/C.
    """
    project_id = str(uuid.uuid4())
    job_id = uuid.uuid4().hex

    try:
        graph = _builder.from_structured_input(request, run_id=job_id, job_id=job_id)
    except Exception as exc:
        logger.error("structured_input_failed", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.utcnow()
    response = BuildingGraphResponse(
        project_id=project_id,
        created_at=now,
        updated_at=now,
        building_graph=graph,
    )
    _register(project_id, job_id, response)
    logger.info("building_created", project_id=project_id, job_id=job_id)
    return response


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("/{project_id}", response_model=BuildingGraphResponse)
async def get_building(project_id: str) -> BuildingGraphResponse:
    """Retrieve a previously created Building Graph."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return _store[project_id]


# ---------------------------------------------------------------------------
# Grid update
# ---------------------------------------------------------------------------


@router.put("/{project_id}/grid", response_model=BuildingGraphResponse)
async def update_grid(
    project_id: str,
    modification: GridModificationRequest,
) -> BuildingGraphResponse:
    """Modify the grid of an existing Building Graph and recompute affected fields.

    Provenance on the regenerated column candidates is preserved against
    the original job's ``run_id`` so the audit trail still links back to
    the structured-form submission that created the project.
    """
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    existing = _store[project_id]
    bg = existing.building_graph

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

    run_id = bg.metadata.job_id or uuid.uuid4().hex
    provenance = structured_form_provenance(
        run_id=run_id, notes="grid regenerated via PUT /grid"
    )
    new_columns = _builder.zone_classifier.identify_columns(new_grid, walls=bg.walls)
    for c in new_columns:
        c.provenance = provenance

    updated_bg = bg.model_copy(
        update={"grid": new_grid, "column_candidates": new_columns}
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


# ---------------------------------------------------------------------------
# Assumption override
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/assumptions/{assumption_id}/override",
    response_model=BuildingGraphResponse,
)
async def override_assumption(
    project_id: str,
    assumption_id: str,
    payload: AssumptionOverrideRequest,
) -> BuildingGraphResponse:
    """Record a human override on a single ``AssumptionRecord``.

    Mutates the stored graph's ``metadata.assumption_register`` in place:
    flips ``was_overridden=True``, records ``override_value`` and
    ``override_source``.  Returns the full updated response so the
    frontend can refresh without a second round-trip.

    Fails 404 if the project does not exist, 404 if the assumption id is
    not in the register, 422 if the assumption is flagged
    ``overrideable=False``.
    """
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    existing = _store[project_id]
    register = existing.building_graph.metadata.assumption_register

    try:
        result = apply_override(
            register,
            assumption_id=assumption_id,
            value=payload.value,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Assumption {assumption_id!r} not found in project {project_id}",
        )

    existing.updated_at = datetime.utcnow()
    logger.info(
        "assumption_overridden",
        project_id=project_id,
        assumption_id=assumption_id,
        source=payload.source,
    )
    return existing


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{project_id}", status_code=204)
async def delete_building(project_id: str) -> None:
    """Delete a stored Building Graph."""
    if project_id not in _store:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    stale = _store.pop(project_id)
    stale_job_id = stale.building_graph.metadata.job_id
    if stale_job_id and _job_index.get(stale_job_id) == project_id:
        _job_index.pop(stale_job_id, None)
    logger.info("building_deleted", project_id=project_id)
