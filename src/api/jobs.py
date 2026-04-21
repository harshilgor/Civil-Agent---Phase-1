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

The ``/review`` sub-endpoint lives here too (both GET and POST) so a
single router owns the job-level review surface for every channel.
Step 11 extended POST to apply element-level corrections alongside
assumption overrides and added GET to surface low-confidence elements
+ the completeness gate in one round-trip.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException

from src.api import async_job_store
from src.core.assumption_builder import apply_override
from src.core.review_service import (
    ReviewCorrectionError,
    apply_corrections,
    build_review_snapshot,
)
from src.schema.input_models import (
    BuildingGraphResponse,
    JobReviewRequest,
    JobStatusResponse,
    ReviewSnapshotResponse,
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


def _resolve_job_for_review(job_id: str):
    """Shared resolver for the review endpoints.

    Returns ``(response, async_record, graph, status)`` where exactly one
    of ``response`` / ``async_record`` is populated and ``graph`` points
    at the same :class:`BuildingGraph` for both channels.  Raises the
    same ``404`` / ``409`` the existing submit-review flow did.
    """

    response = channel_a._lookup_by_job(job_id)
    if response is not None:
        return response, None, response.building_graph, "completed"

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
    return None, async_record, async_record.building_graph, async_record.status


@router.get("/{job_id}/review", response_model=ReviewSnapshotResponse)
async def get_review_snapshot(job_id: str) -> ReviewSnapshotResponse:
    """Return the review queue payload for a finished job.

    Surfaces (a) the completeness gate — ``review_required`` is ``True``
    when overall completeness is below
    :data:`~src.utils.completeness_scorer.HUMAN_REVIEW_THRESHOLD` — and
    (b) every low-confidence element the reviewer should look at, plus
    (c) the overrideable slice of the assumption register, sorted
    weakest-first.  One round-trip, one snapshot — the frontend does
    not need to walk the graph itself.

    Works for Channel A (synchronous) and Channels B/C (async, via the
    :mod:`async_job_store`).  Returns 404 on unknown job ids and 409
    when the target job hasn't produced a graph yet (queued / failed
    Channel-B or Channel-C).
    """

    _response, _async_record, graph, status = _resolve_job_for_review(job_id)
    return build_review_snapshot(job_id=job_id, status=status, bg=graph)


@router.post("/{job_id}/review", response_model=BuildingGraphResponse)
async def submit_review(job_id: str, payload: JobReviewRequest) -> BuildingGraphResponse:
    """Apply a batch of reviewer inputs — assumption overrides and/or
    element-level corrections — to a finished job's Building Graph.

    Step 4 shipped this endpoint for assumption overrides only.  Step 11
    extends it with element-level ``corrections`` that touch walls,
    rooms, openings, columns, or cores directly.  The request body
    accepts both and must contain at least one non-empty list.

    Overrides are applied first (they're cheaper and can't invalidate
    the schema), then corrections.  The first failure aborts the batch
    with 422 (validation / bad target) or 404 (unknown assumption /
    element id) and leaves the graph with whatever landed before the
    failure — same semantics as Step 4 so the frontend can diff against
    its last-known state.

    Every touched element is stamped with a ``USER_OVERRIDE`` provenance
    record (``confidence_from_model=1.0``) and its element-level
    ``confidence`` is clamped to ``1.0`` — human-approved data is
    authoritative.
    """

    response, async_record, graph, _status = _resolve_job_for_review(job_id)
    register = graph.metadata.assumption_register
    reviewer_suffix = f":{payload.reviewer}" if payload.reviewer else ""
    run_id = graph.metadata.job_id or job_id

    applied_overrides: list[str] = []
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
        applied_overrides.append(item.assumption_id)

    applied_corrections: list[str] = []
    if payload.corrections:
        try:
            applied_corrections = apply_corrections(
                graph,
                payload.corrections,
                run_id=run_id,
                reviewer=payload.reviewer,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReviewCorrectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "job_reviewed",
        job_id=job_id,
        reviewer=payload.reviewer,
        overrides=applied_overrides,
        corrections=applied_corrections,
    )

    if response is not None:
        response.updated_at = datetime.utcnow()
        return response

    assert async_record is not None and async_record.building_graph is not None
    async_record._touch()  # type: ignore[attr-defined]
    return BuildingGraphResponse(
        project_id=async_record.job_id,
        created_at=async_record.created_at,
        updated_at=async_record.updated_at,
        building_graph=async_record.building_graph,
    )
