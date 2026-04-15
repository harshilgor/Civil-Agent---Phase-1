"""Job lifecycle: create, update status, store results."""

from __future__ import annotations

from typing import Any

from backend.storage.image_store import ImageStore
from backend.storage.job_store import JobRecord, JobStatus, JobStore
from backend.storage.result_store import ResultStore


class JobService:
    def __init__(self, jobs: JobStore, results: ResultStore, images: ImageStore) -> None:
        self.jobs = jobs
        self.results = results
        self.images = images

    def create_job(self, meta: dict[str, Any] | None = None) -> JobRecord:
        return self.jobs.create(meta)

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def set_running(self, job_id: str, stage: str, progress_pct: float) -> JobRecord | None:
        return self.jobs.update(
            job_id,
            status=JobStatus.RUNNING,
            current_stage=stage,
            progress_pct=progress_pct,
        )

    def complete(self, job_id: str, result: dict[str, Any]) -> JobRecord | None:
        self.results.put(job_id, result)
        return self.jobs.update(job_id, status=JobStatus.COMPLETED, progress_pct=100.0, current_stage="done")

    def fail(self, job_id: str, message: str) -> JobRecord | None:
        return self.jobs.update(job_id, status=JobStatus.FAILED, error_message=message)
