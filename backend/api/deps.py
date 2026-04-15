"""Dependency injection: job store, task queue hooks."""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.edit_service import EditService
from backend.services.export_service import ExportService
from backend.services.job_service import JobService
from backend.services.quantity_service import QuantityService
from backend.storage.image_store import ImageStore
from backend.storage.job_store import JobStore
from backend.storage.result_store import ResultStore


@dataclass
class AppServices:
    jobs: JobStore
    results: ResultStore
    images: ImageStore
    job_service: JobService
    edit_service: EditService
    export_service: ExportService
    quantity_service: QuantityService


_services: AppServices | None = None


def get_services() -> AppServices:
    global _services
    if _services is None:
        jobs = JobStore()
        results = ResultStore()
        images = ImageStore()
        _services = AppServices(
            jobs=jobs,
            results=results,
            images=images,
            job_service=JobService(jobs, results, images),
            edit_service=EditService(results),
            export_service=ExportService(),
            quantity_service=QuantityService(),
        )
    return _services


def get_job_service() -> JobService:
    return get_services().job_service


def get_edit_service() -> EditService:
    return get_services().edit_service


def get_export_service() -> ExportService:
    return get_services().export_service


def get_result_store() -> ResultStore:
    return get_services().results


def get_image_store() -> ImageStore:
    return get_services().images
