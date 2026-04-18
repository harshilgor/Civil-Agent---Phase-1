"""Extract and clean wall segments from raw DXF parser output.

Handles centerline computation for parallel line pairs and merging of
collinear segments.
"""

from __future__ import annotations

import math

import structlog

from src.utils.geometry import distance_2d, line_angle_degrees, segments_collinear

logger = structlog.get_logger(__name__)


class WallExtractor:
    """Post-process raw wall lines into clean centerline segments."""

    def __init__(
        self,
        merge_angle_tol_deg: float = 5.0,
        merge_dist_tol_mm: float = 100.0,
        min_wall_length_mm: float = 200.0,
    ) -> None:
        self._angle_tol = merge_angle_tol_deg
        self._dist_tol = merge_dist_tol_mm
        self._min_len = min_wall_length_mm

    def extract(self, raw_walls: list[dict]) -> list[dict]:
        """Merge collinear segments and remove very short noise lines.

        Returns a list of ``{start, end, thickness_mm}`` dicts.
        """
        # Filter out tiny segments
        walls = [
            w for w in raw_walls
            if distance_2d(w["start"], w["end"]) >= self._min_len
        ]

        merged = self._merge_collinear(walls)
        logger.info("walls_extracted", raw=len(raw_walls), filtered=len(walls), merged=len(merged))
        return merged

    def _merge_collinear(self, walls: list[dict]) -> list[dict]:
        """Group collinear walls and merge overlapping segments."""
        used = [False] * len(walls)
        merged: list[dict] = []

        for i, w1 in enumerate(walls):
            if used[i]:
                continue
            group = [w1]
            used[i] = True
            for j in range(i + 1, len(walls)):
                if used[j]:
                    continue
                if segments_collinear(
                    w1["start"], w1["end"],
                    walls[j]["start"], walls[j]["end"],
                    self._angle_tol, self._dist_tol,
                ):
                    group.append(walls[j])
                    used[j] = True

            merged.append(self._merge_group(group))

        return merged

    @staticmethod
    def _merge_group(group: list[dict]) -> dict:
        """Merge a group of collinear segments into one spanning segment."""
        if len(group) == 1:
            return group[0]

        # Project all endpoints onto the dominant direction
        all_pts = []
        for w in group:
            all_pts.append(w["start"])
            all_pts.append(w["end"])

        # Use the first segment's direction
        angle = math.atan2(
            group[0]["end"][1] - group[0]["start"][1],
            group[0]["end"][0] - group[0]["start"][0],
        )
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        projections = []
        for pt in all_pts:
            proj = pt[0] * cos_a + pt[1] * sin_a
            projections.append((proj, pt))

        projections.sort(key=lambda x: x[0])
        start_pt = projections[0][1]
        end_pt = projections[-1][1]

        avg_thickness = sum(w["thickness_mm"] for w in group) / len(group)

        return {
            "start": start_pt,
            "end": end_pt,
            "thickness_mm": round(avg_thickness, 2),
        }
