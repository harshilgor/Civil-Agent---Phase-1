"""Raster segmentation mask → vector geometry conversion.

Converts binary wall masks and room instance masks into clean vector
segments and polygons using skeletonisation, Hough transform, merging,
snapping, and regularisation.

All geometric tolerances are defined in **real-world millimeters** and then
converted to pixels at runtime using the scale factor from the OCR/unit
inference pipeline. This makes the vectorizer scale-invariant — a plan at
96 DPI and a plan at 300 DPI produce geometrically equivalent output.

If no scale factor is available (OCR found no dimensions), we fall back to
assuming the image represents a building footprint between 10m and 100m
wide; the output is flagged low-confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np
import structlog

from src.utils.geometry import line_angle_degrees, snap_angle

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class VectorizationConfig:
    """All tolerances in millimeters; pixel equivalents are derived at runtime."""

    endpoint_snap_mm: float = 50.0         # ~typical wall thickness
    collinear_merge_mm: float = 100.0
    collinear_angle_deg: float = 5.0       # stays angular
    thickness_measure_mm: float = 25.0
    polygon_closure_mm: float = 75.0
    min_segment_length_mm: float = 200.0

    # Scale fallback (used only when OCR fails to produce any scale factor)
    fallback_building_width_m_min: float = 10.0
    fallback_building_width_m_max: float = 100.0


DEFAULT_CONFIG = VectorizationConfig()


@dataclass
class VectorizationStats:
    scale_mm_per_px: float
    scale_was_inferred: bool
    raw_lines: int
    merged_lines: int
    final_segments: int
    confidence: float


class Vectorizer:
    """Convert raster masks to vector geometry with scale-aware tolerances."""

    def __init__(self, config: VectorizationConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        self.last_stats: VectorizationStats | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def vectorize(
        self,
        wall_mask: np.ndarray,
        scale_mm_per_px: float | None = None,
    ) -> list[dict]:
        """Convert binary wall mask to vector wall segments.

        If *scale_mm_per_px* is None, a heuristic scale is inferred from the
        mask width and the vectorization is flagged low-confidence.
        """
        inferred = False
        if scale_mm_per_px is None or scale_mm_per_px <= 0:
            scale_mm_per_px = self._infer_fallback_scale(wall_mask)
            inferred = True
            logger.warning("vectorizer_scale_fallback", scale_mm_per_px=scale_mm_per_px)

        tolerances = self._compute_pixel_tolerances(scale_mm_per_px)

        # 1. Skeletonise
        skeleton = self._skeletonize(wall_mask)

        # 2. Probabilistic Hough Transform
        raw_lines = self._hough_lines(skeleton, min_len_px=tolerances["min_segment_px"])
        if not raw_lines:
            logger.warning("vectorizer_no_lines")
            self.last_stats = VectorizationStats(
                scale_mm_per_px=scale_mm_per_px,
                scale_was_inferred=inferred,
                raw_lines=0,
                merged_lines=0,
                final_segments=0,
                confidence=0.0,
            )
            return []

        # 3. Merge collinear segments
        merged = self._merge_collinear(raw_lines, tolerances)

        # 4. Snap endpoints
        snapped = self._snap_endpoints(merged, tolerances)

        # 5. Regularise angles
        regularised = self._regularize_angles(snapped, self.config.collinear_angle_deg)

        # 6. Measure thickness and emit segments in mm
        segments: list[dict] = []
        for seg in regularised:
            thickness_px = self._measure_thickness(
                wall_mask, seg, search_px=tolerances["thickness_search_px"]
            )
            segments.append({
                "start": [seg[0] * scale_mm_per_px, seg[1] * scale_mm_per_px],
                "end": [seg[2] * scale_mm_per_px, seg[3] * scale_mm_per_px],
                "thickness_mm": max(thickness_px * scale_mm_per_px, 50),
            })

        confidence = 0.30 if inferred else 1.0
        self.last_stats = VectorizationStats(
            scale_mm_per_px=scale_mm_per_px,
            scale_was_inferred=inferred,
            raw_lines=len(raw_lines),
            merged_lines=len(merged),
            final_segments=len(segments),
            confidence=confidence,
        )
        logger.info(
            "vectorized",
            raw=len(raw_lines),
            merged=len(merged),
            final=len(segments),
            scale_mm_per_px=round(scale_mm_per_px, 4),
            inferred_scale=inferred,
        )
        return segments

    def masks_to_polygons(
        self,
        room_masks: dict[int, np.ndarray],
        scale_mm_per_px: float = 1.0,
        epsilon_factor: float = 0.005,
    ) -> list[dict]:
        """Convert room instance masks to simplified polygons."""
        polygons: list[dict] = []
        for room_id, mask in room_masks.items():
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            perimeter = cv2.arcLength(contour, True)
            epsilon = epsilon_factor * perimeter
            approx = cv2.approxPolyDP(contour, epsilon, True)

            pts = [
                [float(pt[0][0]) * scale_mm_per_px, float(pt[0][1]) * scale_mm_per_px]
                for pt in approx
            ]
            if len(pts) >= 3:
                pts.append(pts[0])
                area = cv2.contourArea(contour) * (scale_mm_per_px ** 2) / 1_000_000
                polygons.append({
                    "room_id": room_id,
                    "polygon": pts,
                    "area_m2": round(area, 2),
                })

        logger.info("polygons_extracted", count=len(polygons))
        return polygons

    # ------------------------------------------------------------------
    # Scale-aware tolerance derivation
    # ------------------------------------------------------------------

    def _compute_pixel_tolerances(self, scale_mm_per_px: float) -> dict[str, float]:
        """Convert every mm-based tolerance into pixels using *scale_mm_per_px*."""
        c = self.config
        return {
            "endpoint_snap_px": c.endpoint_snap_mm / scale_mm_per_px,
            "collinear_merge_px": c.collinear_merge_mm / scale_mm_per_px,
            "thickness_search_px": max(
                10, int(c.thickness_measure_mm / scale_mm_per_px)
            ),
            "polygon_closure_px": c.polygon_closure_mm / scale_mm_per_px,
            "min_segment_px": max(5, int(c.min_segment_length_mm / scale_mm_per_px)),
        }

    def _infer_fallback_scale(self, mask: np.ndarray) -> float:
        """Heuristic scale when OCR found no dimensions.

        Assume the mask width represents a building footprint whose real
        width is the midpoint of ``fallback_building_width_m``.
        """
        width_px = mask.shape[1]
        midpoint_m = (
            self.config.fallback_building_width_m_min
            + self.config.fallback_building_width_m_max
        ) / 2
        width_mm = midpoint_m * 1000
        return width_mm / max(width_px, 1)

    # ------------------------------------------------------------------
    # Sub-pipeline steps
    # ------------------------------------------------------------------

    @staticmethod
    def _skeletonize(mask: np.ndarray) -> np.ndarray:
        skel = np.zeros_like(mask)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        temp = mask.copy()
        while True:
            eroded = cv2.erode(temp, element)
            opened = cv2.dilate(eroded, element)
            diff = cv2.subtract(temp, opened)
            skel = cv2.bitwise_or(skel, diff)
            temp = eroded.copy()
            if cv2.countNonZero(temp) == 0:
                break
        return skel

    @staticmethod
    def _hough_lines(
        skeleton: np.ndarray, min_len_px: int
    ) -> list[tuple[int, int, int, int]]:
        lines = cv2.HoughLinesP(
            skeleton, 1, np.pi / 180,
            threshold=30,
            minLineLength=int(max(min_len_px, 5)),
            maxLineGap=int(max(min_len_px * 0.75, 5)),
        )
        if lines is None:
            return []
        return [tuple(int(v) for v in l[0]) for l in lines]

    @staticmethod
    def _merge_collinear(
        lines: list[tuple[int, int, int, int]],
        tol: dict[str, float],
    ) -> list[tuple[int, int, int, int]]:
        if not lines:
            return []

        used = [False] * len(lines)
        merged: list[tuple[int, int, int, int]] = []

        for i, L1 in enumerate(lines):
            if used[i]:
                continue
            group = [L1]
            used[i] = True
            a1 = line_angle_degrees(L1[:2], L1[2:])

            for j in range(i + 1, len(lines)):
                if used[j]:
                    continue
                L2 = lines[j]
                a2 = line_angle_degrees(L2[:2], L2[2:])
                angle_diff = min(abs(a1 - a2), 180 - abs(a1 - a2))
                if angle_diff > 5:
                    continue
                mid1 = ((L1[0] + L1[2]) / 2, (L1[1] + L1[3]) / 2)
                mid2 = ((L2[0] + L2[2]) / 2, (L2[1] + L2[3]) / 2)
                perp = abs(
                    (mid2[0] - mid1[0]) * math.sin(math.radians(a1))
                    - (mid2[1] - mid1[1]) * math.cos(math.radians(a1))
                )
                if perp < tol["collinear_merge_px"]:
                    group.append(L2)
                    used[j] = True

            merged.append(Vectorizer._merge_line_group(group))
        return merged

    @staticmethod
    def _merge_line_group(
        group: list[tuple[int, int, int, int]]
    ) -> tuple[int, int, int, int]:
        if len(group) == 1:
            return group[0]
        all_pts = []
        for L in group:
            all_pts.append((L[0], L[1]))
            all_pts.append((L[2], L[3]))
        dx = group[0][2] - group[0][0]
        dy = group[0][3] - group[0][1]
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        projections = [(p[0] * ux + p[1] * uy, p) for p in all_pts]
        projections.sort(key=lambda x: x[0])
        start = projections[0][1]
        end = projections[-1][1]
        return (start[0], start[1], end[0], end[1])

    @staticmethod
    def _snap_endpoints(
        lines: list[tuple[int, int, int, int]],
        tol: dict[str, float],
    ) -> list[tuple[int, int, int, int]]:
        points: list[list[float]] = []
        for L in lines:
            points.append([float(L[0]), float(L[1])])
            points.append([float(L[2]), float(L[3])])

        clusters: list[list[int]] = []
        assigned = [False] * len(points)
        snap_tol = tol["endpoint_snap_px"]
        for i in range(len(points)):
            if assigned[i]:
                continue
            cluster = [i]
            assigned[i] = True
            for j in range(i + 1, len(points)):
                if assigned[j]:
                    continue
                dist = math.hypot(points[j][0] - points[i][0], points[j][1] - points[i][1])
                if dist < snap_tol:
                    cluster.append(j)
                    assigned[j] = True
            clusters.append(cluster)

        centroids = {}
        for cluster in clusters:
            cx = sum(points[k][0] for k in cluster) / len(cluster)
            cy = sum(points[k][1] for k in cluster) / len(cluster)
            for k in cluster:
                centroids[k] = (round(cx), round(cy))

        result = []
        for idx, L in enumerate(lines):
            s = centroids[idx * 2]
            e = centroids[idx * 2 + 1]
            result.append((s[0], s[1], e[0], e[1]))
        return result

    @staticmethod
    def _regularize_angles(
        lines: list[tuple[int, int, int, int]],
        angle_tol_deg: float,
    ) -> list[tuple[int, int, int, int]]:
        result = []
        for L in lines:
            angle = line_angle_degrees(L[:2], L[2:])
            snapped = snap_angle(angle, angle_tol_deg)
            if abs(angle - snapped) < 0.1:
                result.append(L)
                continue
            cx = (L[0] + L[2]) / 2
            cy = (L[1] + L[3]) / 2
            half_len = math.hypot(L[2] - L[0], L[3] - L[1]) / 2
            rad = math.radians(snapped)
            dx = half_len * math.cos(rad)
            dy = half_len * math.sin(rad)
            result.append((
                round(cx - dx), round(cy - dy),
                round(cx + dx), round(cy + dy),
            ))
        return result

    @staticmethod
    def _measure_thickness(
        mask: np.ndarray,
        seg: tuple[int, int, int, int],
        search_px: int = 50,
    ) -> float:
        mx = (seg[0] + seg[2]) // 2
        my = (seg[1] + seg[3]) // 2
        dx = seg[2] - seg[0]
        dy = seg[3] - seg[1]
        length = math.hypot(dx, dy) or 1

        nx = -dy / length
        ny = dx / length

        h, w = mask.shape[:2]
        count = 0
        for d in range(-search_px, search_px + 1):
            px = int(mx + d * nx)
            py = int(my + d * ny)
            if 0 <= px < w and 0 <= py < h and mask[py, px] > 0:
                count += 1
        return max(count, 1)


__all__ = ["DEFAULT_CONFIG", "Vectorizer", "VectorizationConfig", "VectorizationStats"]
