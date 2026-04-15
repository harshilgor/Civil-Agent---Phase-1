"""Celery/RQ worker entry: run pipeline, push progress (integrate with WS/redis pubsub)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Celery app stub — replace with real broker URL from settings.
# from celery import Celery
# celery_app = Celery("civil_agent", broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))


def run_pipeline_task(job_id: str, image_path: str, project_root: str) -> dict[str, Any]:
    """Synchronous pipeline run for worker processes."""
    from backend.api.deps import get_services
    from backend.pipeline import run_pipeline

    svc = get_services().job_service
    path = Path(image_path)
    root = Path(project_root)
    try:
        svc.set_running(job_id, "pipeline", 10.0)
        meta = run_pipeline(path, config_dir=root / "config")
        result = {
            "pipeline": meta,
            "rooms": [],
            "boundaries": [],
            "scale": None,
            "metadata": {},
        }
        svc.complete(job_id, result)
        return result
    except Exception as e:  # noqa: BLE001
        svc.fail(job_id, str(e))
        raise
