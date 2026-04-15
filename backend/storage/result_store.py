"""Pipeline outputs: rooms, boundaries, diagnostics (S3/local/DB)."""

from __future__ import annotations

from threading import Lock
from typing import Any


class ResultStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_job: dict[str, dict[str, Any]] = {}

    def put(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._by_job[job_id] = payload

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._by_job.get(job_id)
