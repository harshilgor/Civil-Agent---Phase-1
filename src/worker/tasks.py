"""Celery tasks for async CV processing (Gap 7).

Tasks log structured JSON with: task_id, plan_id, stage, duration_ms,
confidence_mean, error (if any).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from src.worker.celery_app import MODELS, celery_app

logger = structlog.get_logger(__name__)


if celery_app is not None:

    @celery_app.task(bind=True, name="civil_agent.process_floor_plan")
    def process_floor_plan(self, plan_id: str, image_path: str) -> dict[str, Any]:
        """Run the full CV pipeline on *image_path* and return a Building Graph dict.

        Stages: preprocess → wall segment → room segment → OCR → vectorize →
        grid → assemble. Each stage logs its duration and mean confidence.
        """
        from src.cv.pipeline import CVPipeline

        task_id = self.request.id
        t_start = time.perf_counter()

        def _log_stage(stage: str, duration_ms: float, confidence_mean: float | None = None,
                       error: str | None = None) -> None:
            logger.info(
                "task_stage",
                task_id=task_id,
                plan_id=plan_id,
                stage=stage,
                duration_ms=round(duration_ms, 2),
                confidence_mean=confidence_mean,
                error=error,
            )

        try:
            # Instantiate a pipeline that reuses pre-loaded models
            pipeline = _build_pipeline_from_models()
            t = time.perf_counter()
            graph = pipeline.process(Path(image_path))
            _log_stage(
                "pipeline",
                (time.perf_counter() - t) * 1000,
                confidence_mean=graph.metadata.confidence_scores.overall or 0.0,
            )
            result = graph.model_dump(mode="json")
            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "task_complete",
                task_id=task_id,
                plan_id=plan_id,
                duration_ms=round(total_ms, 2),
            )
            return {"status": "ok", "plan_id": plan_id, "building_graph": result}
        except Exception as exc:
            total_ms = (time.perf_counter() - t_start) * 1000
            _log_stage("failed", total_ms, error=str(exc))
            raise

    def _build_pipeline_from_models():
        """Construct a CVPipeline whose modules reuse the globally-loaded models."""
        from src.cv.pipeline import CVPipeline

        pipeline = CVPipeline()
        # Inject pre-loaded models
        if "wall_segmenter" in MODELS:
            pipeline.wall_segmenter = MODELS["wall_segmenter"]
        if "room_segmenter" in MODELS:
            pipeline.room_segmenter = MODELS["room_segmenter"]
        if "symbol_detector" in MODELS:
            pipeline.symbol_detector = MODELS["symbol_detector"]
        if "ocr_extractor" in MODELS:
            pipeline.ocr_extractor = MODELS["ocr_extractor"]
        return pipeline


__all__ = ["process_floor_plan"] if celery_app is not None else []
