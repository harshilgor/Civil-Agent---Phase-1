"""OCR text and dimension extraction from floor-plan images.

Uses PaddleOCR when available, falls back to a regex-based stub.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from src.cv.unit_inferrer import UnitInferrer, UnitSystem

logger = structlog.get_logger(__name__)

# Regex patterns for floor-plan text classification
_DIM_PATTERN = re.compile(
    r"^[\d,]+\.?\d*\s*(mm|cm|m|ft|in|\'|\")?$|"  # "6000", "6.5m"
    r"^\d+\'-\d+\"?$|"                              # "20'-0\""
    r"^\d+[,\.]\d+$"                                # "6,000"
)
_GRID_LABEL_PATTERN = re.compile(r"^[A-Z]{1,2}$|^\d{1,2}$")
_ANNOTATION_PATTERN = re.compile(r"^(UP|DN|TYP|EQ|SIM|NTS|REF)$", re.IGNORECASE)


def normalize_paddle_ocr_output(raw: Any) -> Any:
    """Convert PaddleOCR 3.x / PaddleX ``OCRResult`` pages to the legacy nested list."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        return raw
    first = raw[0]
    if not hasattr(first, "json"):
        return raw
    legacy_pages: list[list[Any]] = []
    for page in raw:
        j = page.json if isinstance(getattr(page, "json", None), dict) else {}
        res = j.get("res", j) if isinstance(j, dict) else {}
        rec_texts = res.get("rec_texts") or []
        rec_scores = res.get("rec_scores") or []
        polys = res.get("rec_polys") or []
        items: list[Any] = []
        for i, t in enumerate(rec_texts):
            conf = float(rec_scores[i]) if i < len(rec_scores) else 1.0
            bbox = polys[i] if i < len(polys) else [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
            items.append([bbox, (str(t), conf)])
        legacy_pages.append(items)
    return legacy_pages


def paddle_ocr_raw(paddle: Any, image: np.ndarray) -> Any:
    """Run PaddleOCR across 2.x (``ocr``) and 3.x (``ocr``/``predict``) APIs."""
    if paddle is None:
        return None
    raw: Any = None
    ocr_fn = getattr(paddle, "ocr", None)
    if callable(ocr_fn):
        try:
            raw = ocr_fn(image, cls=True)
        except TypeError:
            try:
                raw = ocr_fn(image)
            except Exception as exc:
                logger.warning("paddle_ocr_call_failed", error=str(exc))
    if raw is None:
        pred = getattr(paddle, "predict", None)
        if callable(pred):
            try:
                raw = pred(image)
            except Exception as exc:
                logger.warning("paddle_predict_failed", error=str(exc))
    return normalize_paddle_ocr_output(raw)


class OCRExtractor:
    """Extract text, dimensions, and labels from a floor-plan image."""

    def __init__(self, use_gpu: bool = False, use_ensemble: bool = True) -> None:
        self._ocr = None
        self._ensemble = None
        self._unit_inferrer = UnitInferrer()
        try:
            from paddleocr import PaddleOCR

            try:
                self._ocr = PaddleOCR(
                    use_angle_cls=True, lang="en", use_gpu=use_gpu, show_log=False
                )
            except (TypeError, ValueError):
                try:
                    self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                except (TypeError, ValueError):
                    try:
                        self._ocr = PaddleOCR(use_angle_cls=True, lang="en")
                    except (TypeError, ValueError):
                        self._ocr = PaddleOCR(lang="en")
            logger.info("paddleocr_loaded")
        except ImportError:
            logger.warning("paddleocr_not_available")
        if use_ensemble:
            try:
                from src.cv.ocr_ensemble import OCREnsemble

                self._ensemble = OCREnsemble(paddle_engine=self._ocr)
                logger.info("ocr_ensemble_enabled")
            except ImportError as exc:
                logger.warning("ocr_ensemble_unavailable", error=str(exc))

    def extract(self, image: np.ndarray) -> dict[str, Any]:
        """Run OCR and classify results.

        Returns::

            {
                "dimensions": [...],
                "room_labels": [...],
                "grid_labels": [...],
                "annotations": [...],
                "all_text": [...],
                "scale_factor": float | None
            }
        """
        if self._ensemble is not None:
            texts = self._ensemble.run(image)
        elif self._ocr is not None:
            raw = paddle_ocr_raw(self._ocr, image)
            texts = self._parse_paddle_results(raw)
        else:
            texts = []
            logger.warning("ocr_skipped_no_engine")

        dimensions: list[dict] = []
        room_labels: list[dict] = []
        grid_labels: list[dict] = []
        annotations: list[dict] = []
        dim_strings: list[str] = []

        for t in texts:
            text = t["text"]
            if _DIM_PATTERN.match(text):
                dim_strings.append(text)
                dimensions.append({**t})
            elif _GRID_LABEL_PATTERN.match(text):
                grid_labels.append(t)
            elif _ANNOTATION_PATTERN.match(text):
                annotations.append(t)
            elif len(text) > 2:
                room_labels.append(t)

        # Run unit inference on all dimension strings together, then convert
        unit_info = self._unit_inferrer.infer(dim_strings)
        for dim in dimensions:
            dim["value_mm"] = self._convert_with_unit_info(dim["text"], unit_info)
            dim["unit_system"] = unit_info.unit_system.value
            dim["unit_confidence"] = unit_info.confidence

        scale_factor = self._estimate_scale(dimensions) if dimensions else None

        logger.info(
            "ocr_extracted",
            dims=len(dimensions),
            rooms=len(room_labels),
            grids=len(grid_labels),
        )
        return {
            "dimensions": dimensions,
            "room_labels": room_labels,
            "grid_labels": grid_labels,
            "annotations": annotations,
            "all_text": texts,
            "scale_factor": scale_factor,
            "unit_info": unit_info.to_dict(),
        }

    # ------------------------------------------------------------------
    # Unit-aware dimension conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_with_unit_info(text: str, unit_info) -> float | None:
        """Convert a single OCR dimension string to mm using the drawing's
        inferred unit system.

        * Imperial strings like ``20'-0"`` are always parsed directly.
        * Plain numeric values are multiplied by the drawing's conversion factor.
        """
        clean = text.replace(",", "").strip()

        m = re.match(r"(\d+)['\u2019]-?(\d+)?[\"\u2033]?", clean)
        if m:
            feet = float(m.group(1))
            inches = float(m.group(2) or 0)
            return round(feet * 304.8 + inches * 25.4, 2)

        m = re.match(r"([\d.]+)\s*(mm|cm|m|ft|in)", clean, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            factors = {"mm": 1, "cm": 10, "m": 1000, "ft": 304.8, "in": 25.4}
            return round(val * factors.get(unit, 1), 2)

        m = re.match(r"^([\d.]+)$", clean)
        if m:
            try:
                val = float(m.group(1))
                if unit_info.unit_system == UnitSystem.FEET_INCHES:
                    return round(val * 304.8, 2)
                return round(val * unit_info.conversion_factor_to_mm, 2)
            except ValueError:
                return None
        return None

    def associate_dimensions(
        self,
        text_data: dict[str, Any],
        wall_segments: list[dict],
    ) -> list[dict]:
        """Link dimension values to their nearest wall/span.

        Returns a list of ``{dimension, wall_index, distance}`` associations.
        """
        associations: list[dict] = []
        for dim in text_data.get("dimensions", []):
            pos = dim.get("position", [0, 0])
            best_idx = -1
            best_dist = float("inf")
            for idx, wall in enumerate(wall_segments):
                mid = [
                    (wall["start"][0] + wall["end"][0]) / 2,
                    (wall["start"][1] + wall["end"][1]) / 2,
                ]
                dist = ((pos[0] - mid[0]) ** 2 + (pos[1] - mid[1]) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

            if best_idx >= 0:
                associations.append({
                    "dimension": dim,
                    "wall_index": best_idx,
                    "distance_px": round(best_dist, 2),
                })
        return associations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_paddle_results(raw: list) -> list[dict]:
        texts: list[dict] = []
        if not raw or not raw[0]:
            return texts
        for item in raw[0]:
            bbox, (text, confidence) = item
            cx = sum(p[0] for p in bbox) / 4
            cy = sum(p[1] for p in bbox) / 4
            texts.append({
                "text": text.strip(),
                "position": [round(cx, 1), round(cy, 1)],
                "confidence": round(confidence, 3),
                "bbox": bbox,
            })
        return texts

    @staticmethod
    def _parse_dimension_value(text: str) -> float | None:
        """Extract numeric mm value from dimension text."""
        clean = text.replace(",", "").strip()

        # Imperial: 20'-0"
        m = re.match(r"(\d+)['\u2019]-?(\d+)[\"″]?", clean)
        if m:
            feet, inches = float(m.group(1)), float(m.group(2))
            return round(feet * 304.8 + inches * 25.4, 2)

        # Metric with unit
        m = re.match(r"([\d.]+)\s*(mm|cm|m|ft|in)", clean, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            factors = {"mm": 1, "cm": 10, "m": 1000, "ft": 304.8, "in": 25.4}
            return round(val * factors.get(unit, 1), 2)

        # Plain number (assume mm)
        m = re.match(r"^([\d.]+)$", clean)
        if m:
            return float(m.group(1))

        return None

    @staticmethod
    def _estimate_scale(dimensions: list[dict]) -> float | None:
        """Estimate mm-per-pixel scale factor from dimension annotations.

        Requires at least one dimension with a known value and a bbox size
        to compute the ratio.
        """
        for dim in dimensions:
            value_mm = dim.get("value_mm")
            bbox = dim.get("bbox")
            if value_mm and bbox and value_mm > 0:
                # Width of the dimension text bbox approximates the span
                x_coords = [p[0] for p in bbox]
                span_px = max(x_coords) - min(x_coords)
                if span_px > 10:
                    return round(value_mm / span_px, 4)
        return None
