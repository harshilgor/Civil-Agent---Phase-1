"""Unified jobs endpoint.

Channel A (structured form) returns a result synchronously; Channels B
(CAD upload) and C (floor-plan image) return a ``job_id`` and complete
asynchronously.  The frontend does not need to know which channel
produced a result — it polls ``GET /api/v1/jobs/{job_id}`` until
``status == "completed"`` and then reads the embedded ``building_graph``.

Resolution order:

1. :mod:`src.api.structured_input` (Channel A's synchronous store).
2. :mod:`src.api.async_job_store` (Channels B/C, reconciled against
   live Celery state on every call).

Only when both miss do we return 404.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException

from src.api import async_job_store
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


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll-friendly status for a Channel A/B/C job.

    For Channel A the result is always ``completed`` on the first call
    (the structured-form endpoint is synchronous and stores the graph
    before returning).  Channels B/C start at ``queued`` / ``processing``
    and flip to ``completed`` (with ``building_graph`` inlined) or
    ``failed`` once the worker reports.  Unknown ids return 404.
    """

    channel_a_hit = channel_a._lookup_by_job(job_id)
    if channel_a_hit is not None:
        return JobStatusResponse(
            job_id=job_id,
            status="completed",
            progress_percent=100.0,
            result_id=channel_a_hit.project_id,
            error=None,
            building_graph=channel_a_hit.building_graph,
        )

    async_record = async_job_store.refresh(job_id)
    if async_record is not None:
        return JobStatusResponse(
            job_id=job_id,
            status=async_record.status,
            progress_percent=async_record.progress_percent,
            result_id=async_record.job_id if async_record.status == "completed" else None,
            error=async_record.error,
            building_graph=async_record.building_graph,
        )

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@router.post("/{job_id}/review", response_model=BuildingGraphResponse)
async def submit_review(job_id: str, payload: JobReviewRequest) -> BuildingGraphResponse:
    """Apply a batch of assumption overrides from the review step.

    All overrides are applied in order; the first one that fails (unknown
    id or ``overrideable=False``) aborts the batch with 422 / 404 and
    leaves the graph unchanged below that point.  The response reflects
    whatever overrides landed before the failure so the frontend can
    diff against its last-known state.

    Works for both Channel A (synchronous, BuildingGraphResponse-backed)
    and Channels B/C (async, BuildingGraph-backed via
    :mod:`src.api.async_job_store`).
    """

    response = channel_a._lookup_by_job(job_id)
    async_record = None
    if response is None:
        async_record = async_job_store.refresh(job_id)
        if async_record is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        if async_record.building_graph is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Job {job_id} is in state {async_record.status!r}; "
                    "cannot review before the graph is complete."
                ),
            )

    graph = (
        response.building_graph if response is not None else async_record.building_graph  # type: ignore[union-attr]
    )
    register = graph.metadata.assumption_register
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

    logger.info(
        "job_reviewed",
        job_id=job_id,
        reviewer=payload.reviewer,
        overrides=applied,
    )
    if response is not None:
        response.updated_at = datetime.utcnow()
        return response

    # Async path: synthesise a BuildingGraphResponse around the stored
    # graph so the contract stays identical across channels.
    assert async_record is not None and async_record.building_graph is not None
    async_record._touch()  # type: ignore[attr-defined]
    return BuildingGraphResponse(
        project_id=async_record.job_id,
        created_at=async_record.created_at,
        updated_at=async_record.updated_at,
        building_graph=async_record.building_graph,
    )
