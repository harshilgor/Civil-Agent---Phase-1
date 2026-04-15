"""Job metadata + status (Postgres or Redis in production)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any
from uuid import uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobRecord:
    id: str
    status: JobStatus = JobStatus.QUEUED
    progress_pct: float = 0.0
    current_stage: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class JobStore:
    """In-memory job index; swap for Redis/Postgres."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, JobRecord] = {}

    def create(self, meta: dict[str, Any] | None = None) -> JobRecord:
        jid = str(uuid4())
        rec = JobRecord(id=jid, meta=meta or {})
        with self._lock:
            self._jobs[jid] = rec
        return rec

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress_pct: float | None = None,
        current_stage: str | None = None,
        error_message: str | None = None,
    ) -> JobRecord | None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return None
            if status is not None:
                rec.status = status
            if progress_pct is not None:
                rec.progress_pct = progress_pct
            if current_stage is not None:
                rec.current_stage = current_stage
            if error_message is not None:
                rec.error_message = error_message
            rec.updated_at = datetime.now(timezone.utc)
            return rec
