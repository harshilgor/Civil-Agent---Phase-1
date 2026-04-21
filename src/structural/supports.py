"""Support candidate generation and forbidden region detection.

Given a ``BuildingGraph`` this module emits:

* ``SupportCandidate`` points (potential column/wall locations) classified
  into STRONG / SECONDARY / WEAK / FORBIDDEN.
* ``ForbiddenRegion`` polygons around elevators, stairs, corridors etc.

The algorithm is scoring-based, not decision-based — the final placement of
supports is deferred to later phases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from src.schema.building_graph import BuildingGraph, Core, Story
from src.schema.enums import CoreType, RoomType, WallType
from src.schema.structural_enums import (
    ForbiddenReason,
    SupportCandidateClass,
    SupportCandidateReason,
)
from src.schema.structural_graph import (
    ForbiddenRegion,
    StructuralZone,
    SupportCandidate,
)
from src.structural.config import DEFAULT_CONFIG, StructuralConfig

logger = logging.getLogger(__name__)


@dataclass
class _CandidateScore:
    position: tuple[float, float]
    base: float
    reasons: list[SupportCandidateReason]
    grid_intersection: str | None = None


class SupportCandidateGenerator:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> tuple[list[SupportCandidate], list[ForbiddenRegion]]:
        forbidden = self._compute_forbidden_regions(graph)
        candidates: list[SupportCandidate] = []

        for story in graph.stories:
            story_forbidden = [f for f in forbidden if f.story == story.id]
            raw = self._raw_candidates(graph, story)
            for raw_c in raw:
                cand = self._score_and_classify(
                    raw_c,
                    graph=graph,
                    story=story,
                    forbidden_regions=story_forbidden,
                )
                candidates.append(cand)

        return candidates, forbidden

    # ------------------------------------------------------------------
    # Forbidden regions
    # ------------------------------------------------------------------

    def _compute_forbidden_regions(self, graph: BuildingGraph) -> list[ForbiddenRegion]:
        cfg = self.config.supports
        regions: list[ForbiddenRegion] = []

        for core in graph.cores:
            stories = core.stories or [s.id for s in graph.stories]
            if core.contains_elevator or core.type in {CoreType.ELEVATOR_STAIR, CoreType.ELEVATOR_ONLY}:
                poly = self._buffer_polygon(core.polygon, cfg.elevator_buffer_mm)
                reason = ForbiddenReason.ELEVATOR_SHAFT
            elif core.contains_stairs or core.type == CoreType.STAIR_ONLY:
                poly = self._buffer_polygon(core.polygon, cfg.stair_buffer_mm)
                reason = ForbiddenReason.STAIR_OPENING
            else:
                continue
            for story_id in stories:
                regions.append(
                    ForbiddenRegion(
                        id=f"fr-{core.id}-{story_id}",
                        polygon=poly,
                        story=story_id,
                        reason=reason,
                        notes=f"Buffer around {core.type.value}",
                    )
                )

        for room in graph.rooms:
            if room.type == RoomType.CORRIDOR:
                poly = Polygon(room.polygon)
                minx, miny, maxx, maxy = poly.bounds
                width = min(maxx - minx, maxy - miny)
                if width < self.config.zoning.narrow_corridor_width_mm:
                    regions.append(
                        ForbiddenRegion(
                            id=f"fr-corr-{room.id}",
                            polygon=room.polygon,
                            story=room.story,
                            reason=ForbiddenReason.PRIMARY_CORRIDOR,
                            notes=f"Narrow corridor width {width:.0f}mm",
                        )
                    )
            elif room.type == RoomType.LOBBY and room.area_m2 > 40.0:
                regions.append(
                    ForbiddenRegion(
                        id=f"fr-lobby-{room.id}",
                        polygon=room.polygon,
                        story=room.story,
                        reason=ForbiddenReason.LOBBY_CLEARANCE,
                        notes="Lobby clear span required",
                    )
                )

        return regions

    @staticmethod
    def _buffer_polygon(polygon: list[list[float]], buffer_mm: float) -> list[list[float]]:
        try:
            poly = Polygon(polygon).buffer(buffer_mm)
            if poly.is_empty:
                return polygon
            return [list(pt) for pt in poly.exterior.coords]
        except Exception:
            return polygon

    # ------------------------------------------------------------------
    # Raw candidate generation
    # ------------------------------------------------------------------

    def _raw_candidates(self, graph: BuildingGraph, story: Story) -> list[_CandidateScore]:
        cfg = self.config.supports
        out: list[_CandidateScore] = []
        seen: set[tuple[int, int]] = set()

        def add(x: float, y: float, base: float, reasons: list[SupportCandidateReason],
                grid_intersection: str | None = None) -> None:
            key = (round(x / 100), round(y / 100))
            if key in seen:
                return
            seen.add(key)
            out.append(_CandidateScore(
                position=(x, y),
                base=base,
                reasons=reasons,
                grid_intersection=grid_intersection,
            ))

        # 1. Existing column candidates from Phase 1
        for col in graph.column_candidates:
            reasons = [SupportCandidateReason.GRID_INTERSECTION] if col.grid_intersection else []
            if not reasons:
                reasons = [SupportCandidateReason.WALL_ALIGNMENT]
            add(col.position[0], col.position[1],
                base=cfg.base_score_wall_intersection if col.grid_intersection is None
                else cfg.base_score_grid_intersection,
                reasons=reasons,
                grid_intersection=col.grid_intersection)

        # 2. Grid intersections
        for gx in graph.grid.x_lines:
            for gy in graph.grid.y_lines:
                add(
                    gx.position_mm,
                    gy.position_mm,
                    base=cfg.base_score_grid_intersection,
                    reasons=[SupportCandidateReason.GRID_INTERSECTION],
                    grid_intersection=f"{gx.id}-{gy.id}",
                )

        # 3. Core corners (for stories where core exists)
        for core in graph.cores:
            if core.stories and story.id not in core.stories:
                continue
            for pt in core.polygon:
                add(pt[0], pt[1], base=cfg.base_score_core_corner,
                    reasons=[SupportCandidateReason.CORE_ADJACENCY])

        # 4. Facade corners
        for pt in graph.facade.perimeter_polygon:
            add(pt[0], pt[1], base=cfg.base_score_perimeter_corner,
                reasons=[SupportCandidateReason.PERIMETER_CORNER])

        # 5. Wall intersections (structural walls only)
        intersections = _wall_intersections(
            [w for w in graph.walls if w.type in {WallType.STRUCTURAL, WallType.SHEAR_WALL}
             and story.id in w.stories]
        )
        for (x, y) in intersections:
            add(x, y, base=cfg.base_score_wall_intersection,
                reasons=[SupportCandidateReason.WALL_ALIGNMENT])

        return out

    # ------------------------------------------------------------------
    # Scoring + classification
    # ------------------------------------------------------------------

    def _score_and_classify(
        self,
        raw: _CandidateScore,
        *,
        graph: BuildingGraph,
        story: Story,
        forbidden_regions: list[ForbiddenRegion],
    ) -> SupportCandidate:
        cfg = self.config.supports
        x, y = raw.position
        pt = Point(x, y)
        penalties: list[str] = []
        score = raw.base

        # Grid alignment boost
        dist_to_grid = self._dist_to_grid_intersection(x, y, graph)
        if dist_to_grid <= cfg.grid_align_within_mm:
            score *= 1.10
        elif dist_to_grid >= cfg.grid_align_decay_at_mm:
            score *= 0.85

        # Forbidden-region check
        in_forbidden = False
        for fr in forbidden_regions:
            try:
                poly = Polygon(fr.polygon)
                if poly.contains(pt) or poly.touches(pt):
                    in_forbidden = True
                    penalties.append(f"inside_{fr.reason.value}")
                    score = 0.0
                    break
            except Exception:
                continue

        # Classification
        score = max(0.0, min(1.0, score))
        if in_forbidden:
            cls = SupportCandidateClass.FORBIDDEN
        elif score >= cfg.strong_threshold:
            cls = SupportCandidateClass.STRONG
        elif score >= cfg.secondary_threshold:
            cls = SupportCandidateClass.SECONDARY
        elif score >= cfg.weak_threshold:
            cls = SupportCandidateClass.WEAK
        else:
            cls = SupportCandidateClass.WEAK

        return SupportCandidate(
            id=f"sup-{story.id}-{int(x)}-{int(y)}",
            position=[x, y],
            story=story.id,
            classification=cls,
            score=score,
            reasons=raw.reasons,
            penalties=penalties,
            grid_intersection=raw.grid_intersection,
        )

    @staticmethod
    def _dist_to_grid_intersection(x: float, y: float, graph: BuildingGraph) -> float:
        if not graph.grid.x_lines or not graph.grid.y_lines:
            return float("inf")
        dx = min(abs(x - gx.position_mm) for gx in graph.grid.x_lines)
        dy = min(abs(y - gy.position_mm) for gy in graph.grid.y_lines)
        return (dx ** 2 + dy ** 2) ** 0.5


# ---------------------------------------------------------------------------
# Helper: wall-wall intersection finder
# ---------------------------------------------------------------------------

def _wall_intersections(walls: list) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i, w1 in enumerate(walls):
        for w2 in walls[i + 1:]:
            pt = _segment_intersection(w1.start, w1.end, w2.start, w2.end)
            if pt is not None:
                out.append(pt)
    return out


def _segment_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None
