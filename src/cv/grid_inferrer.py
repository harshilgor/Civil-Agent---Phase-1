"""Infer structural grid from detected wall segments + OCR grid labels.

Two-stage algorithm:

1. **OCR-first path** — if the OCR pipeline extracted grid labels
   (single letters A-Z or numbers 1-99 at drawing edges), use their spatial
   positions as direct evidence of grid line locations. Validate against
   wall centerlines.
2. **Geometric fallback** — when OCR labels are absent or incomplete, run
   the original angle-clustering / projection algorithm.

Output includes provenance (``source`` per grid line: ``"ocr"`` or
``"geometric"``) and confidence.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

from src.schema.building_graph import GridLine

logger = structlog.get_logger(__name__)


_LETTER_LABEL = re.compile(r"^[A-Z]{1,2}$")
_NUMBER_LABEL = re.compile(r"^\d{1,2}$")

EDGE_BAND_FRAC = 0.12  # a label in the top 12% of the image is an "edge" label
WALL_ALIGNMENT_TOLERANCE_MM = 500.0


@dataclass
class GridLabelCandidate:
    label: str
    position_xy_mm: tuple[float, float]
    kind: str  # "letter" or "number"


class GridInferrer:
    """Infer the structural grid from walls and (optionally) OCR labels."""

    def __init__(
        self,
        cluster_eps_mm: float = 400,
        min_walls_per_line: int = 2,
        regularity_threshold: float = 0.10,
    ) -> None:
        self._eps = cluster_eps_mm
        self._min_walls = min_walls_per_line
        self._reg_thresh = regularity_threshold

    def infer(
        self,
        wall_segments: list[dict],
        ocr_text: list[dict[str, Any]] | None = None,
        image_size_px: tuple[int, int] | None = None,
        scale_mm_per_px: float | None = None,
    ) -> dict:
        """Infer grid.

        Parameters
        ----------
        wall_segments: list of ``{start, end, ...}`` dicts in mm.
        ocr_text: all OCR text detections from the plan. Grid labels are
            filtered out inside this method.
        image_size_px: ``(width, height)`` of the source raster image.
        scale_mm_per_px: conversion factor (needed to place OCR pixel
            coordinates into the same mm-space as walls).
        """
        ocr_result = None
        if ocr_text and image_size_px and scale_mm_per_px:
            ocr_result = self._grid_from_ocr(
                ocr_text, image_size_px, scale_mm_per_px, wall_segments
            )

        geometric = self._grid_from_geometry(wall_segments)

        x_lines, x_source = self._merge_direction(
            ocr=ocr_result.get("x_lines") if ocr_result else None,
            geometric=geometric["x_lines"],
        )
        y_lines, y_source = self._merge_direction(
            ocr=ocr_result.get("y_lines") if ocr_result else None,
            geometric=geometric["y_lines"],
        )

        is_regular = self._check_regularity(
            [gl.position_mm for gl in x_lines]
        ) and self._check_regularity(
            [gl.position_mm for gl in y_lines]
        )

        base_conf = geometric["confidence"]
        # Boost confidence when OCR labels corroborate geometry
        if x_source == "ocr" or y_source == "ocr":
            confidence = min(1.0, base_conf + 0.15)
        else:
            confidence = base_conf

        logger.info(
            "grid_inferred",
            x_lines=len(x_lines),
            y_lines=len(y_lines),
            x_source=x_source,
            y_source=y_source,
            regular=is_regular,
            confidence=round(confidence, 3),
        )
        return {
            "x_lines": x_lines,
            "y_lines": y_lines,
            "is_regular": is_regular,
            "confidence": round(confidence, 3),
            "x_source": x_source,
            "y_source": y_source,
        }

    # ------------------------------------------------------------------
    # OCR-based grid detection
    # ------------------------------------------------------------------

    def _grid_from_ocr(
        self,
        ocr_text: list[dict[str, Any]],
        image_size_px: tuple[int, int],
        scale_mm_per_px: float,
        wall_segments: list[dict],
    ) -> dict:
        """Extract grid label candidates and turn them into GridLines."""
        w_px, h_px = image_size_px
        top_band = h_px * EDGE_BAND_FRAC
        bottom_band = h_px * (1 - EDGE_BAND_FRAC)
        left_band = w_px * EDGE_BAND_FRAC
        right_band = w_px * (1 - EDGE_BAND_FRAC)

        x_candidates: list[GridLabelCandidate] = []
        y_candidates: list[GridLabelCandidate] = []

        for t in ocr_text:
            text = str(t.get("text", "")).strip().upper()
            if not text:
                continue
            pos = t.get("position", [0, 0])
            px, py = float(pos[0]), float(pos[1])

            is_letter = bool(_LETTER_LABEL.match(text))
            is_number = bool(_NUMBER_LABEL.match(text))
            if not (is_letter or is_number):
                continue

            on_top_or_bottom = py < top_band or py > bottom_band
            on_left_or_right = px < left_band or px > right_band

            # Convention A: letters top/bottom → X grid, numbers left/right → Y grid
            # Convention B: swap. We pick whichever yields the larger set.
            if on_top_or_bottom and is_letter:
                x_candidates.append(
                    GridLabelCandidate(
                        label=text,
                        position_xy_mm=(px * scale_mm_per_px, py * scale_mm_per_px),
                        kind="letter",
                    )
                )
            elif on_left_or_right and is_number:
                y_candidates.append(
                    GridLabelCandidate(
                        label=text,
                        position_xy_mm=(px * scale_mm_per_px, py * scale_mm_per_px),
                        kind="number",
                    )
                )
            elif on_top_or_bottom and is_number:
                # Convention B fallback
                x_candidates.append(
                    GridLabelCandidate(
                        label=text,
                        position_xy_mm=(px * scale_mm_per_px, py * scale_mm_per_px),
                        kind="number",
                    )
                )
            elif on_left_or_right and is_letter:
                y_candidates.append(
                    GridLabelCandidate(
                        label=text,
                        position_xy_mm=(px * scale_mm_per_px, py * scale_mm_per_px),
                        kind="letter",
                    )
                )

        x_lines = self._labels_to_grid_lines(x_candidates, axis="x", wall_segments=wall_segments)
        y_lines = self._labels_to_grid_lines(y_candidates, axis="y", wall_segments=wall_segments)

        logger.info(
            "ocr_grid_extracted",
            x_labels=len(x_candidates),
            y_labels=len(y_candidates),
            x_lines=len(x_lines),
            y_lines=len(y_lines),
        )
        return {"x_lines": x_lines, "y_lines": y_lines}

    def _labels_to_grid_lines(
        self,
        candidates: list[GridLabelCandidate],
        axis: str,
        wall_segments: list[dict],
    ) -> list[GridLine]:
        if not candidates:
            return []
        # Collapse duplicate labels (same character at multiple edge positions)
        by_label: dict[str, list[float]] = {}
        for c in candidates:
            # For x-axis grid lines, the label's X position is the grid line
            coord = c.position_xy_mm[0] if axis == "x" else c.position_xy_mm[1]
            by_label.setdefault(c.label, []).append(coord)

        # Average positions per label; sort by position
        items = [(label, sum(ps) / len(ps)) for label, ps in by_label.items()]
        items.sort(key=lambda x: x[1])

        # Validate sequentiality (A, B, C... or 1, 2, 3...)
        is_sequential = self._check_sequential(items)
        if not is_sequential:
            logger.warning("ocr_grid_labels_not_sequential", labels=[i[0] for i in items])

        # Validate alignment with wall centerlines
        aligned_items = [
            (label, pos) for label, pos in items
            if self._aligns_with_walls(pos, axis, wall_segments)
        ]
        if not aligned_items and items:
            # No walls to validate against — keep all labels
            aligned_items = items

        return [GridLine(id=label, position_mm=round(pos, 2)) for label, pos in aligned_items]

    @staticmethod
    def _check_sequential(items: list[tuple[str, float]]) -> bool:
        """Check labels follow an alphabetic or numeric sequence."""
        labels = [l for l, _ in items]
        if not labels:
            return True
        # Numeric sequence
        if all(l.isdigit() for l in labels):
            try:
                nums = [int(l) for l in labels]
                return all(b >= a for a, b in zip(nums, nums[1:]))
            except ValueError:
                return False
        # Alphabetic sequence
        if all(l.isalpha() and len(l) == 1 for l in labels):
            return all(b >= a for a, b in zip(labels, labels[1:]))
        return True  # mixed/unknown — be permissive

    @staticmethod
    def _aligns_with_walls(pos_mm: float, axis: str, walls: list[dict]) -> bool:
        if not walls:
            return True
        for w in walls:
            wall_axis_start = w["start"][0] if axis == "x" else w["start"][1]
            wall_axis_end = w["end"][0] if axis == "x" else w["end"][1]
            if (
                abs(wall_axis_start - pos_mm) < WALL_ALIGNMENT_TOLERANCE_MM
                or abs(wall_axis_end - pos_mm) < WALL_ALIGNMENT_TOLERANCE_MM
            ):
                return True
        return False

    @staticmethod
    def _merge_direction(
        ocr: list[GridLine] | None,
        geometric: list[GridLine],
    ) -> tuple[list[GridLine], str]:
        """Prefer OCR when it produced at least 2 lines; otherwise use geometry."""
        if ocr and len(ocr) >= 2:
            return ocr, "ocr"
        return geometric, "geometric"

    # ------------------------------------------------------------------
    # Geometric fallback (original algorithm)
    # ------------------------------------------------------------------

    def _grid_from_geometry(self, wall_segments: list[dict]) -> dict:
        if not wall_segments:
            return {"x_lines": [], "y_lines": [], "confidence": 0.0}

        angles: list[float] = []
        for w in wall_segments:
            dx = w["end"][0] - w["start"][0]
            dy = w["end"][1] - w["start"][1]
            angle = math.degrees(math.atan2(dy, dx)) % 180
            angles.append(angle)

        dominant_h, dominant_v = self._find_dominant_directions(angles)

        x_positions = self._project_axis(wall_segments, dominant_v, axis="x")
        y_positions = self._project_axis(wall_segments, dominant_h, axis="y")

        x_clusters = self._cluster_1d(x_positions)
        y_clusters = self._cluster_1d(y_positions)

        x_lines = [
            GridLine(id=chr(65 + i) if i < 26 else f"X{i + 1}", position_mm=round(pos, 2))
            for i, pos in enumerate(sorted(x_clusters))
        ]
        y_lines = [
            GridLine(id=str(i + 1), position_mm=round(pos, 2))
            for i, pos in enumerate(sorted(y_clusters))
        ]

        aligned_count = sum(
            1 for a in angles
            if min(abs(a - dominant_h), 180 - abs(a - dominant_h)) < 10
            or min(abs(a - dominant_v), 180 - abs(a - dominant_v)) < 10
        )
        confidence = aligned_count / max(len(angles), 1)

        return {
            "x_lines": x_lines,
            "y_lines": y_lines,
            "confidence": round(confidence, 3),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_dominant_directions(angles: list[float]) -> tuple[float, float]:
        buckets: Counter[int] = Counter()
        for a in angles:
            bucket = round(a / 5) * 5
            buckets[bucket] += 1

        if not buckets:
            return 0.0, 90.0

        most_common = buckets.most_common(1)[0][0]
        perp = (most_common + 90) % 180
        return float(most_common), float(perp)

    def _project_axis(
        self, walls: list[dict], direction_deg: float, axis: str
    ) -> list[float]:
        positions: list[float] = []
        for w in walls:
            dx = w["end"][0] - w["start"][0]
            dy = w["end"][1] - w["start"][1]
            wall_angle = math.degrees(math.atan2(dy, dx)) % 180
            angle_diff = min(abs(wall_angle - direction_deg), 180 - abs(wall_angle - direction_deg))
            if angle_diff > 15:
                continue

            if axis == "x":
                positions.append(w["start"][0])
                positions.append(w["end"][0])
            else:
                positions.append(w["start"][1])
                positions.append(w["end"][1])
        return positions

    def _cluster_1d(self, values: list[float]) -> list[float]:
        if not values:
            return []
        sorted_vals = sorted(values)
        clusters: list[list[float]] = [[sorted_vals[0]]]

        for v in sorted_vals[1:]:
            if v - clusters[-1][-1] <= self._eps:
                clusters[-1].append(v)
            else:
                clusters.append([v])

        return [
            sum(c) / len(c)
            for c in clusters
            if len(c) >= self._min_walls
        ]

    def _check_regularity(self, positions: list[float]) -> bool:
        if len(positions) < 3:
            return True

        sorted_pos = sorted(positions)
        spacings = [sorted_pos[i + 1] - sorted_pos[i] for i in range(len(sorted_pos) - 1)]
        mean = sum(spacings) / len(spacings)
        if mean == 0:
            return True
        std = (sum((s - mean) ** 2 for s in spacings) / len(spacings)) ** 0.5
        return (std / mean) < self._reg_thresh
