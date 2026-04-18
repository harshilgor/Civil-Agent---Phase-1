"""Celery application for Civil Agent's async CV pipeline.

V1 design (Gap 7): **Redis-only** broker + result backend. No RabbitMQ.

Key GPU-task behavior:
  * ``worker_prefetch_multiplier = 1`` — every task needs the full GPU.
  * ``task_acks_late = True`` — never acknowledge before work completes.
  * ``task_track_started = True`` — emit STARTED so the frontend can render progress.
  * ``task_reject_on_worker_lost = True`` — requeue on worker crash.
  * ``task_time_limit = 300`` / ``task_soft_time_limit = 240`` — 5-/4-minute limits.

Models (U-Net, YOLOv8, SAM, PaddleOCR) are loaded ONCE at worker startup via
the ``worker_init`` signal and kept as module globals; tasks access them
directly, avoiding the 10-30s per-task load cost.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import structlog

try:
    from celery import Celery
    from celery.signals import task_failure, task_postrun, task_prerun, worker_init

    _HAS_CELERY = True
except ImportError:  # pragma: no cover
    Celery = object  # type: ignore
    _HAS_CELERY = False

from src.config import settings

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Celery app factory
# ---------------------------------------------------------------------------


def make_celery() -> "Celery":
    if not _HAS_CELERY:
        raise RuntimeError(
            "Celery is not installed. Install the 'worker' extra: pip install civil-agent[worker]"
        )

    app = Celery(
        "civil_agent",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["src.worker.tasks"],
    )

    app.conf.update(
        # Broker / backend
        broker_connection_retry_on_startup=True,
        result_expires=60 * 60 * 24,  # keep results for 24h
        # GPU-critical behavior
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_track_started=True,
        task_reject_on_worker_lost=True,
        task_time_limit=300,
        task_soft_time_limit=240,
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = make_celery() if _HAS_CELERY else None


# ---------------------------------------------------------------------------
# Model registry (populated at worker_init)
# ---------------------------------------------------------------------------


MODELS: dict[str, Any] = {}


if _HAS_CELERY:

    @worker_init.connect
    def _load_models(**_: Any) -> None:
        """Load CV models once per worker process.

        This runs in the Celery worker's main process. Each task then reads
        directly from ``MODELS`` without ever touching disk.
        """
        logger.info("worker_init_loading_models")
        t0 = time.perf_counter()

        # Wall segmenter (U-Net)
        try:
            from src.cv.wall_segmenter import WallSegmenter

            MODELS["wall_segmenter"] = WallSegmenter(
                model_path=settings.wall_segmenter_weights
            )
            logger.info("wall_segmenter_loaded")
        except Exception as exc:
            logger.error("wall_segmenter_load_failed", error=str(exc))

        # Symbol detector (YOLOv8)
        try:
            from src.cv.symbol_detector import SymbolDetector

            MODELS["symbol_detector"] = SymbolDetector(
                model_path=settings.symbol_detector_weights
            )
            logger.info("symbol_detector_loaded")
        except Exception as exc:
            logger.error("symbol_detector_load_failed", error=str(exc))

        # Room segmenter (SAM)
        try:
            from src.cv.room_segmenter import RoomSegmenter

            MODELS["room_segmenter"] = RoomSegmenter()
            logger.info("room_segmenter_loaded")
        except Exception as exc:
            logger.error("room_segmenter_load_failed", error=str(exc))

        # OCR extractor (PaddleOCR + PARSeq ensemble)
        try:
            from src.cv.ocr_extractor import OCRExtractor

            MODELS["ocr_extractor"] = OCRExtractor(use_gpu=False, use_ensemble=True)
            logger.info("ocr_extractor_loaded")
        except Exception as exc:
            logger.error("ocr_extractor_load_failed", error=str(exc))

        logger.info(
            "worker_init_complete",
            elapsed_s=round(time.perf_counter() - t0, 2),
            loaded=list(MODELS.keys()),
        )

    # Structured per-task logging ----------------------------------------

    @task_prerun.connect
    def _task_prerun(task_id: str, task, *, args: Any = None, **_: Any) -> None:  # type: ignore[no-untyped-def]
        logger.info(
            "task_prerun",
            task_id=task_id,
            task_name=task.name,
        )

    @task_postrun.connect
    def _task_postrun(
        task_id: str, task, *, state: str = "SUCCESS", **_: Any
    ) -> None:  # type: ignore[no-untyped-def]
        logger.info(
            "task_postrun",
            task_id=task_id,
            task_name=task.name,
            state=state,
        )

    @task_failure.connect
    def _task_failure(task_id: str, exception, *, traceback=None, **_: Any) -> None:  # type: ignore[no-untyped-def]
        logger.error(
            "task_failure",
            task_id=task_id,
            error=str(exception),
        )


__all__ = ["MODELS", "celery_app", "make_celery"]
