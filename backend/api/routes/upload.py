"""POST /upload — accept floor plan, return job_id, kick off async pipeline."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from backend.api.deps import get_job_service, get_services
from backend.services.job_service import JobService

router = APIRouter(tags=["upload"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_pipeline_job(job_id: str, image_path: Path, mode: str, job_svc: JobService) -> None:
    try:
        job_svc.set_running(job_id, "stage0_input", 10.0)
        from backend.pipeline import run_pipeline

        meta = run_pipeline(image_path, config_dir=PROJECT_ROOT / "config")
        # Preserve source image endpoint in results for the frontend viewer.
        metadata = dict(meta.get("metadata", {}))
        metadata["image_url"] = f"/jobs/{job_id}/image"
        meta["metadata"] = metadata
        meta["pipeline"] = {**meta.get("pipeline", {}), "requested_mode": mode}
        job_svc.complete(job_id, meta)
    except Exception as e:  # noqa: BLE001
        job_svc.fail(job_id, str(e))


@router.post("/upload")
async def upload_floorplan(
    background_tasks: BackgroundTasks,
    mode: str = Form("light"),
    file: UploadFile = File(...),
    job_svc: JobService = Depends(get_job_service),
) -> dict[str, str]:
    services = get_services()
    job = job_svc.create_job(meta={"filename": file.filename, "mode": mode})
    suffix = Path(file.filename or "upload").suffix or ".bin"
    path = services.images.save(job.id, file.file, suffix=suffix)
    background_tasks.add_task(_run_pipeline_job, job.id, path, mode, job_svc)
    return {"job_id": job.id}
