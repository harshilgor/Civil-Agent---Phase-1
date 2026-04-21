"""In-memory registry for Channel B / C asynchronous jobs (Step 5).

Channel A (structured form) resolves synchronously and has its own store
inside :mod:`src.api.structured_input`.  Channels B (CAD upload) and C
(floor-plan image) return ``202 Accepted`` with a ``job_id``; the worker
completes the graph later and writes the result back here.  The unified
:mod:`src.api.jobs` router reads from both stores so the frontend polls
a single endpoint regardless of channel.

The store is deliberately a module-level dict: Phase-1 is single-process
and the DB-backed replacement is on the Step-10 roadmap.  Every mutation
goes through the helpers below so Steps 6+ can swap the backing store
without touching the endpoints.

State machine
-------------

``queued``    — file persisted, Celery task submitted, not yet running
``processing`` — Celery moved the task into STARTED
``completed`` — worker wrote a BuildingGraph back; ``building_graph`` set
``failed``    — worker raised; ``error`` carries the message

Only forward transitions are allowed (``failed`` / ``completed`` are
terminal).  The poller in :mod:`src.api.jobs` calls :func:`refresh`
which reads the live Celery state before returning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from src.schema.building_graph import BuildingGraph

JobStatus = Literal["queued", "processing", "completed", "failed"]
JobChannel = Literal["image", "cad"]

_TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed"})


@dataclass
class AsyncJobRecord:
    """One async job as seen by the status endpoint."""

    job_id: str
    channel: JobChannel
    status: JobStatus = "queued"
    filename: Optional[str] = None
    file_type: Optional[str] = None
    source_path: Optional[str] = None
    celery_task_id: Optional[str] = None
    progress_percent: float = 0.0
    building_graph: Optional[BuildingGraph] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def _touch(self) -> None:
        self.updated_at = datetime.utcnow()

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATES


# Module-level singleton, same pattern as Channel A's ``_store``.
_store: dict[str, AsyncJobRecord] = {}


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def register(
    job_id: str,
    *,
    channel: JobChannel,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
    source_path: Optional[str] = None,
) -> AsyncJobRecord:
    """Create the ``queued`` record that the endpoint hands back as 202."""

    record = AsyncJobRecord(
        job_id=job_id,
        channel=channel,
        status="queued",
        filename=filename,
        file_type=file_type,
        source_path=source_path,
    )
    _store[job_id] = record
    return record


def attach_celery_task(job_id: str, celery_task_id: str) -> Optional[AsyncJobRecord]:
    """Record the Celery task id so we can poll its state later."""

    record = _store.get(job_id)
    if record is None:
        return None
    record.celery_task_id = celery_task_id
    if record.status == "queued":
        record.status = "processing"
        record.progress_percent = 1.0
    record._touch()
    return record


def reconcile_from_async_result(
    job_id: str, async_result: object
) -> Optional[AsyncJobRecord]:
    """Pull terminal state off a just-returned Celery ``AsyncResult``.

    This is the fast path used by both endpoints and the
    ``task_always_eager`` test configuration: after ``.delay()`` we
    already have a live handle to the task's result object, so we avoid
    a round-trip through the result backend (which may not exist in
    eager mode, and is exactly the thing we want to skip in unit tests).

    Non-terminal AsyncResults are left alone; the next
    :func:`refresh` call will reconcile against the backend when one is
    available.
    """

    record = _store.get(job_id)
    if record is None or record.is_terminal():
        return record

    try:
        ready = async_result.ready()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover — defensive
        return record
    if not ready:
        return record

    try:
        succeeded = async_result.successful()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        succeeded = False

    if succeeded:
        try:
            payload = async_result.result  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            return mark_failed(job_id, f"result fetch failed: {exc}")
        graph = _extract_building_graph(payload)
        if graph is None:
            return mark_failed(job_id, "worker returned no building_graph")
        return mark_completed(job_id, graph)

    try:
        info = async_result.result  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        info = None
    return mark_failed(job_id, str(info) if info else "worker raised")


def mark_completed(
    job_id: str, graph: BuildingGraph
) -> Optional[AsyncJobRecord]:
    """Store the worker's :class:`BuildingGraph` and flip to ``completed``."""

    record = _store.get(job_id)
    if record is None:
        return None
    record.status = "completed"
    record.progress_percent = 100.0
    record.building_graph = graph
    record.error = None
    record._touch()
    return record


def mark_failed(job_id: str, error: str) -> Optional[AsyncJobRecord]:
    record = _store.get(job_id)
    if record is None:
        return None
    record.status = "failed"
    record.error = error
    record._touch()
    return record


def mark_processing(
    job_id: str, progress_percent: float = 1.0
) -> Optional[AsyncJobRecord]:
    record = _store.get(job_id)
    if record is None:
        return None
    if record.status == "queued":
        record.status = "processing"
    record.progress_percent = max(record.progress_percent, progress_percent)
    record._touch()
    return record


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def get(job_id: str) -> Optional[AsyncJobRecord]:
    return _store.get(job_id)


def _celery_state_to_status(state: str) -> JobStatus:
    """Translate a Celery state string to our external status vocabulary."""

    state = (state or "").upper()
    if state in {"SUCCESS"}:
        return "completed"
    if state in {"FAILURE", "REVOKED"}:
        return "failed"
    if state in {"STARTED", "RETRY"}:
        return "processing"
    # PENDING, RECEIVED or anything unknown → queued (conservative default).
    return "queued"


def refresh(job_id: str) -> Optional[AsyncJobRecord]:
    """Reconcile the record against live Celery state, if available.

    This is a read-time sync: the endpoint calls it before serialising a
    :class:`JobStatusResponse`.  It is a no-op when

    * Celery isn't installed (unit-test mode), or
    * the record has no ``celery_task_id`` yet, or
    * the record is already in a terminal state.

    Successful tasks have their ``BuildingGraph`` rehydrated from the
    result backend into :attr:`AsyncJobRecord.building_graph`.  Failures
    copy the exception repr into :attr:`AsyncJobRecord.error`.
    """

    record = _store.get(job_id)
    if record is None:
        return None
    if record.is_terminal() or not record.celery_task_id:
        return record

    try:
        from src.worker.celery_app import celery_app
    except Exception:  # pragma: no cover — defensive
        return record
    if celery_app is None:
        return record

    try:
        ar = celery_app.AsyncResult(record.celery_task_id)
        state = ar.state or ""
    except Exception:  # pragma: no cover — broker outage
        return record

    new_status = _celery_state_to_status(state)
    if new_status == "completed":
        try:
            payload = ar.result
        except Exception as exc:  # pragma: no cover
            return mark_failed(job_id, f"result fetch failed: {exc}")
        graph = _extract_building_graph(payload)
        if graph is None:
            return mark_failed(job_id, "worker returned no building_graph")
        return mark_completed(job_id, graph)

    if new_status == "failed":
        info = ar.info
        return mark_failed(job_id, str(info) if info else "worker raised")

    # Still running — just bump the status if it has moved forward.
    if new_status == "processing" and record.status == "queued":
        mark_processing(job_id)
    return record


def _extract_building_graph(payload: object) -> Optional[BuildingGraph]:
    """Rehydrate a :class:`BuildingGraph` from a worker's return value."""

    if payload is None:
        return None
    if isinstance(payload, BuildingGraph):
        return payload
    if isinstance(payload, dict):
        if "building_graph" in payload and isinstance(payload["building_graph"], dict):
            return BuildingGraph.model_validate(payload["building_graph"])
        try:
            return BuildingGraph.model_validate(payload)
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _reset_for_tests() -> None:
    """Clear the module-level store; used by the pytest fixtures."""

    _store.clear()


__all__ = [
    "AsyncJobRecord",
    "JobChannel",
    "JobStatus",
    "attach_celery_task",
    "get",
    "mark_completed",
    "mark_failed",
    "mark_processing",
    "reconcile_from_async_result",
    "refresh",
    "register",
]
