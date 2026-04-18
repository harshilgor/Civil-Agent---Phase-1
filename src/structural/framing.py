"""Framing direction inferrer.

Determines the primary (and secondary) framing direction for each
structural zone, based on bay aspect, wall continuity, core placement,
and corridor orientation. Outputs ``FramingZone`` entries.
"""

from __future__ import annotations

import logging
import math

from src.schema.building_graph import BuildingGraph
from src.schema.enums import RoomType, WallType
from src.schema.structural_enums import FramingDirection
from src.schema.structural_graph import FramingZone, SpanMap, StructuralZone
from src.structural.config import DEFAULT_CONFIG, StructuralConfig
from src.utils.geometry import line_angle_degrees

logger = logging.getLogger(__name__)


class FramingDirectionInferrer:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def infer(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
        span_map: SpanMap,
    ) -> list[FramingZone]:
        results: list[FramingZone] = []
        aspect_score = self._aspect_score(span_map)
        wall_score = self._wall_score(graph)
        corridor_score = self._corridor_score(graph)

        for zone in zones:
            core_score = self._core_score(graph, zone)

            cfg = self.config.framing
            combined_score = (
                aspect_score * cfg.bay_aspect_weight
                + wall_score * cfg.wall_continuity_weight
                + core_score * cfg.core_placement_weight
                + corridor_score * cfg.corridor_orientation_weight
            )

            # combined_score > 0 → X dominant; < 0 → Y dominant
            magnitude = abs(combined_score)
            if magnitude < 0.05:
                primary = FramingDirection.BIDIRECTIONAL
                secondary = FramingDirection.BIDIRECTIONAL
            elif combined_score > 0:
                primary = FramingDirection.X_PRIMARY
                secondary = FramingDirection.Y_PRIMARY
            else:
                primary = FramingDirection.Y_PRIMARY
                secondary = FramingDirection.X_PRIMARY

            confidence = min(1.0, magnitude + 0.5)
            rationale = (
                f"aspect={aspect_score:+.2f}, wall={wall_score:+.2f}, "
                f"core={core_score:+.2f}, corridor={corridor_score:+.2f}"
            )

            results.append(
                FramingZone(
                    zone_id=zone.id,
                    primary_direction=primary,
                    secondary_direction=secondary,
                    confidence=confidence,
                    rationale=rationale,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Score helpers: positive → X primary, negative → Y primary
    # ------------------------------------------------------------------

    def _aspect_score(self, span_map: SpanMap) -> float:
        if not span_map.spans:
            return 0.0
        x_longer = sum(1 for s in span_map.spans if s.span_x_mm > s.span_y_mm)
        y_longer = sum(1 for s in span_map.spans if s.span_y_mm > s.span_x_mm)
        total = max(1, len(span_map.spans))
        # Longer span → beams run across shorter direction → primary framing
        # is the *shorter* direction (opposite of longer).
        # Positive → X primary.
        return (y_longer - x_longer) / total

    def _wall_score(self, graph: BuildingGraph) -> float:
        walls = [w for w in graph.walls if w.type in {WallType.STRUCTURAL, WallType.SHEAR_WALL}]
        if not walls:
            return 0.0
        x_len = 0.0
        y_len = 0.0
        for w in walls:
            angle = line_angle_degrees(w.start, w.end)
            length = math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1])
            if angle < 45 or angle > 135:
                x_len += length
            else:
                y_len += length
        total = x_len + y_len
        if total == 0:
            return 0.0
        return (x_len - y_len) / total

    def _corridor_score(self, graph: BuildingGraph) -> float:
        corridors = [r for r in graph.rooms if r.type == RoomType.CORRIDOR]
        if not corridors:
            return 0.0
        score = 0.0
        for c in corridors:
            xs = [p[0] for p in c.polygon]
            ys = [p[1] for p in c.polygon]
            dx = max(xs) - min(xs)
            dy = max(ys) - min(ys)
            if dx > dy:
                score += 1.0  # E-W corridor → X primary
            elif dy > dx:
                score -= 1.0
        return max(-1.0, min(1.0, score / len(corridors)))

    def _core_score(self, graph: BuildingGraph, zone: StructuralZone) -> float:
        if not graph.cores:
            return 0.0
        # Use centroid of first applicable core vs zone centroid
        facade_pts = graph.facade.perimeter_polygon
        if not facade_pts:
            return 0.0
        xs_f = [p[0] for p in facade_pts]
        ys_f = [p[1] for p in facade_pts]
        fx = (min(xs_f) + max(xs_f)) / 2
        fy = (min(ys_f) + max(ys_f)) / 2

        core = graph.cores[0]
        cxs = [p[0] for p in core.polygon]
        cys = [p[1] for p in core.polygon]
        cx = sum(cxs) / len(cxs)
        cy = sum(cys) / len(cys)

        # If core is off-center primarily in X, framing aligns along X → span
        # across the larger gap → Y primary framing.
        dx = abs(cx - fx)
        dy = abs(cy - fy)
        total = dx + dy
        if total < 1e-6:
            return 0.0
        return (dy - dx) / total
