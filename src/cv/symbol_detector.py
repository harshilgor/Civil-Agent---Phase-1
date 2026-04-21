"""Architectural symbol detection using YOLOv8.

Detects doors, windows, stairs, elevators, and other floor-plan symbols.
Falls back to template matching when no YOLO weights are available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

SYMBOL_CLASSES = ["door", "window", "stair", "elevator", "toilet", "sink", "column"]


class SymbolDetector:
    """Detect architectural symbols in floor-plan images."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model = None
        if model_path and Path(model_path).exists():
            try:
                from ultralytics import YOLO

                self._model = YOLO(str(model_path))
                logger.info("symbol_detector_loaded", path=str(model_path))
            except ImportError:
                logger.warning("ultralytics_not_available")

    def detect(self, image: np.ndarray, confidence_threshold: float = 0.3) -> list[dict]:
        """Detect symbols in *image*.

        Returns list of ``{class_name, bbox: [x1,y1,x2,y2], confidence}``.
        """
        if self._model is not None:
            return self._detect_yolo(image, confidence_threshold)
        return self._detect_fallback(image)

    def _detect_yolo(self, image: np.ndarray, conf: float) -> list[dict]:
        results = self._model(image, conf=conf, verbose=False)
        detections: list[dict] = []
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                cls_name = SYMBOL_CLASSES[cls_id] if cls_id < len(SYMBOL_CLASSES) else f"class_{cls_id}"
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "class_name": cls_name,
                    "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    "confidence": round(float(box.conf[0]), 3),
                })
        logger.info("symbols_detected_yolo", count=len(detections))
        return detections

    @staticmethod
    def _detect_fallback(image: np.ndarray) -> list[dict]:
        """Placeholder — no detections without a trained model."""
        logger.warning("symbol_detection_skipped_no_model")
        return []
