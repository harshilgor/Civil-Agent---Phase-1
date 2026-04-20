"""Unified jobs endpoint.

Channel A (structured form) returns a result synchronously, Channel B (CAD
upload) and Channel C (floor-plan image) return a ``job_id`` and process
asynchronously.  The frontend should not need to care which channel
produced a result — it polls ``GET /api/v1/jobs/{job_id}`` until
``status == "completed"`` and then reads the embedded ``building_graph``.

For Channel A the graph is already resolved when the submission returns, so
the jobs endpoint is a simple lookup against
``src.api.structured_input._job_index``.  Channels B/C will add their own
job stores wired into the same registry in Steps 5/6 and beyond.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException

from src.core.assumption_builder import apply_override
from src.schema.input_models import (
    BuildingGraphResponse,
    JobReviewRequest,
    JobStatusResponse,
)

# Local imports from Channel A's module-level store; avoids a circular
# import between this router and structured_input.
from . import structured_input as channel_a

logger = structlog.get_logger(__name__)

router = APIRouter()


def _resolve(job_id: str) -> Optional[BuildingGraphResponse]:
    """Resolve ``job_id`` to a stored :class:`BuildingGraphResponse`.

    Today only Channel A's store is consulted; the async channels will
    register into the same indirection in their follow-up steps so this
    function stays as the single resolution point.
    """

    response = channel_a._lookup_by_job(job_id)
    if response is not None:
        return response
    return None


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll-friendly status for a Channel A/B/C job.

    For Channel A the result is always ``completed`` on the first call
    (the structured-form endpoint is synchronous and stores the graph
    before returning).  Unknown ids return 404 so the frontend can
    distinguish "still processing" (this is not implemented yet — B/C
    will return 200 with status=queued|processing) from "no such job".
    """

    response = _resolve(job_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job_id,
        status="completed",
        progress_percent=100.0,
        result_id=response.project_id,
        error=None,
        building_graph=response.building_graph,
    )


@router.post("/{job_id}/review", response_model=BuildingGraphResponse)
async def submit_review(job_id: str, payload: JobReviewRequest) -> BuildingGraphResponse:
    """Apply a batch of assumption overrides from the review step.

    All overrides are applied in order; the first one that fails (unknown
    id or ``overrideable=False``) aborts the batch with 422 / 404 and
    leaves the graph unchanged below that point.  The response reflects
    whatever overrides landed before the failure so the frontend can
    diff against its last-known state.
    """

    response = _resolve(job_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    register = response.building_graph.metadata.assumption_register
    reviewer_suffix = f":{payload.reviewer}" if payload.reviewer else ""

    applied: list[str] = []
    for item in payload.overrides:
        try:
            updated = apply_override(
                register,
                assumption_id=item.assumption_id,
                value=item.value,
                source=item.source + reviewer_suffix,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Assumption {item.assumption_id!r} not found in the "
                    f"register for job {job_id}"
                ),
            )
        applied.append(item.assumption_id)

    response.updated_at = datetime.utcnow()
    logger.info(
        "job_reviewed",
        job_id=job_id,
        reviewer=payload.reviewer,
        overrides=applied,
    )
    return response
