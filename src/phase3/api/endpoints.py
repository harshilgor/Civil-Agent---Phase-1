"""Phase 3 HTTP endpoints.

Async execution is implemented with an in-process task store for V1. When a
production Celery deployment is available, swap ``_TASK_STORE`` for a Celery
result backend — the public endpoints do not need to change.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..models.inputs import OverrideEntry, Phase3Input
from ..models.outputs import AssumptionRegister, Phase3Output
from ..phase3_service import Phase3Service

router = APIRouter()

_service = Phase3Service()

#: Simple in-memory task store for async runs.
_TASK_STORE: dict[str, dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", tags=["Phase 3"])
async def phase3_health() -> dict[str, str]:
    """Return a Phase 3 liveness probe."""

    return {"status": "ok", "phase": "3", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Synchronous compute
# ---------------------------------------------------------------------------


@router.post(
    "/compute",
    response_model=Phase3Output,
    tags=["Phase 3"],
    summary="Run Phase 3 synchronously",
)
async def compute(phase3_input: Phase3Input) -> Phase3Output:
    """Compute loads synchronously.

    Recommended for small buildings (< 10 stories).
    """

    return _service.run(phase3_input)


# ---------------------------------------------------------------------------
# Asynchronous compute (in-process task store for V1)
# ---------------------------------------------------------------------------


@router.post(
    "/compute/async",
    tags=["Phase 3"],
    summary="Queue a Phase 3 run (in-process V1 scheduler)",
)
async def compute_async(phase3_input: Phase3Input) -> dict[str, str]:
    """Queue a Phase 3 run and return a task id."""

    task_id = str(uuid.uuid4())
    with _TASK_LOCK:
        _TASK_STORE[task_id] = {"status": "queued", "input": phase3_input}

    thread = threading.Thread(
        target=_run_task_worker,
        args=(task_id, phase3_input),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "queued"}


@router.get("/results/{task_id}", tags=["Phase 3"])
async def get_results(task_id: str) -> dict[str, Any]:
    """Return the result of an async Phase 3 run."""

    with _TASK_LOCK:
        entry = _TASK_STORE.get(task_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown task_id '{task_id}'",
        )

    if entry["status"] in ("queued", "running"):
        return {"status": entry["status"]}
    if entry["status"] == "failed":
        return {"status": "failed", "error": entry.get("error", "unknown")}

    output: Phase3Output = entry["result"]
    return {"status": "success", **output.model_dump()}


@router.get("/assumptions/{task_id}", response_model=AssumptionRegister, tags=["Phase 3"])
async def get_assumptions(task_id: str) -> AssumptionRegister:
    """Return the assumption register for a completed task."""

    with _TASK_LOCK:
        entry = _TASK_STORE.get(task_id)
    if entry is None or entry.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not completed.",
        )
    output: Phase3Output = entry["result"]
    return output.assumption_register


@router.post("/override/{task_id}", response_model=Phase3Output, tags=["Phase 3"])
async def apply_overrides(task_id: str, overrides: list[OverrideEntry]) -> Phase3Output:
    """Re-run Phase 3 for the given task with additional overrides."""

    with _TASK_LOCK:
        entry = _TASK_STORE.get(task_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown task_id '{task_id}'",
        )

    phase3_input: Phase3Input = entry["input"]
    updated = _service.rerun_with_overrides(phase3_input, overrides)

    with _TASK_LOCK:
        _TASK_STORE[task_id] = {
            "status": "success",
            "input": phase3_input,
            "result": updated,
        }

    return updated


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _run_task_worker(task_id: str, phase3_input: Phase3Input) -> None:
    """Execute Phase 3 and publish the result to the task store."""

    with _TASK_LOCK:
        _TASK_STORE[task_id]["status"] = "running"
    try:
        result = _service.run(phase3_input)
        with _TASK_LOCK:
            _TASK_STORE[task_id] = {
                "status": "success",
                "input": phase3_input,
                "result": result,
            }
    except Exception as exc:  # propagate as task failure
        with _TASK_LOCK:
            _TASK_STORE[task_id] = {
                "status": "failed",
                "input": phase3_input,
                "error": str(exc),
            }
