"""Column-candidate and core-zone identification.

Analyses a structural grid (and, optionally, rooms and walls) to determine
where columns and vertical-service cores should be placed.

Column scoring now incorporates *wall-type awareness* (Gap 6): intersections
of partition walls are heavily penalised; structural/shear wall
intersections are favoured. Low-confidence wall classifications blend the
multiplier toward 1.0 so they don't overshoot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

from src.schema.building_graph import (
    ColumnCandidate,
    Core,
    GridSystem,
    Room,
    WallSegment,
)
from src.schema.enums import CoreType, RoomType, WallType

logger = structlog.get_logger(__name__)

# Room types that strongly indicate a service core
_CORE_ROOM_TYPES: set[RoomType] = {
    RoomType.STAIRWELL,
    RoomType.ELEVATOR,
    RoomType.MECHANICAL,
    RoomType.BATHROOM,
}


# Wall-type multipliers applied to column candidate scores (Gap 6)
_WALL_TYPE_MULTIPLIERS: dict[tuple[WallType, WallType], float] = {
    (WallType.STRUCTURAL, WallType.STRUCTURAL): 1.0,
    (WallType.STRUCTURAL, WallType.PARTITION): 0.4,
    (WallType.PARTITION, WallType.PARTITION): 0.1,
}

# Wall-type multipliers that depend on ANY of the two walls being of a
# given type (short-circuit overrides)
_OVERRIDE_MULTIPLIERS: list[tuple[WallType, float]] = [
    (WallType.SHEAR_WALL, 1.2),
    (WallType.FACADE, 1.1),
]

# Intersection proximity — a column candidate "uses" a wall pair if both
# walls pass within this distance of the candidate (in mm).
INTERSECTION_PROXIMITY_MM = 500.0

# Minimum wall-type confidence below which we blend toward 1.0
CONFIDENCE_FLOOR = 0.7


@dataclass
class _WallLine:
    """Internal helper — a wall with precomputed line-math."""

    type: WallType
    start: tuple[float, float]
    end: tuple[float, float]
    confidence: float  # per-wall type-classification confidence


class ZoneClassifier:
    """Identify column candidates and core zones."""

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def identify_columns(
        self,
        grid: GridSystem,
        walls: list[WallSegment] | None = None,
        wall_type_confidence: float = 0.9,
        architectural_constraints: list[dict] | None = None,
    ) -> list[ColumnCandidate]:
        """Every grid intersection becomes a column candidate.

        Base scoring heuristic:
          * Corner intersections → required, confidence 1.0
          * Perimeter intersections → confidence 0.95
          * Interior intersections → confidence 0.85

        Then applies a *wall-type multiplier* if ``walls`` are supplied, so
        that partition-wall intersections are penalised relative to
        structural-wall intersections.
        """
        constraints = architectural_constraints or []
        wall_lines = [
            _WallLine(
                type=w.type,
                start=(w.start[0], w.start[1]),
                end=(w.end[0], w.end[1]),
                confidence=wall_type_confidence,
            )
            for w in (walls or [])
        ]

        candidates: list[ColumnCandidate] = []

        x_positions = [gl.position_mm for gl in grid.x_lines]
        y_positions = [gl.position_mm for gl in grid.y_lines]

        x_min, x_max = x_positions[0], x_positions[-1]
        y_min, y_max = y_positions[0], y_positions[-1]

        for xl in grid.x_lines:
            for yl in grid.y_lines:
                x, y = xl.position_mm, yl.position_mm
                is_corner = (x in (x_min, x_max)) and (y in (y_min, y_max))
                is_perimeter = x in (x_min, x_max) or y in (y_min, y_max)

                if is_corner:
                    base_score = 1.0
                    required = True
                elif is_perimeter:
                    base_score = 0.95
                    required = False
                else:
                    base_score = 0.85
                    required = False

                label = f"{xl.id}-{yl.id}"

                # Architectural no-column zones
                for c in constraints:
                    if self._point_in_rect(x, y, c):
                        base_score = max(0.1, base_score - 0.3)
                        break

                # Wall-type multiplier
                wall_mult = self._wall_type_multiplier(x, y, wall_lines, is_perimeter)
                final_score = min(1.0, base_score * wall_mult)

                candidates.append(
                    ColumnCandidate(
                        position=[x, y],
                        grid_intersection=label,
                        confidence=round(final_score, 3),
                        is_required=required,
                        notes=(
                            f"base={base_score:.2f} wall_mult={wall_mult:.2f} "
                            f"wall_type_conf={wall_type_confidence:.2f}"
                        ),
                    )
                )

        logger.info(
            "columns_identified",
            total=len(candidates),
            required=sum(1 for c in candidates if c.is_required),
        )
        return candidates

    def _wall_type_multiplier(
        self,
        x: float,
        y: float,
        walls: list[_WallLine],
        is_perimeter: bool,
    ) -> float:
        """Compute the wall-type multiplier for the candidate at (x, y)."""
        if not walls:
            return 1.0

        nearby = [w for w in walls if self._wall_near_point(w, x, y)]
        if len(nearby) < 2:
            # Not a real intersection of walls
            if is_perimeter and any(w.type == WallType.FACADE for w in nearby):
                return 1.1
            return 1.0

        # Evaluate every pair and take the strongest multiplier
        best_mult = 0.0
        max_conf = 0.0
        for i, w1 in enumerate(nearby):
            for w2 in nearby[i + 1:]:
                mult = self._pair_multiplier(w1.type, w2.type)
                conf = min(w1.confidence, w2.confidence)
                # Blend toward 1.0 when confidence is low
                if conf < CONFIDENCE_FLOOR:
                    mult = conf * mult + (1 - conf) * 1.0
                if mult > best_mult:
                    best_mult = mult
                    max_conf = conf

        if best_mult == 0.0:
            return 1.0
        _ = max_conf  # currently unused but kept for diagnostics
        return best_mult

    @staticmethod
    def _pair_multiplier(a: WallType, b: WallType) -> float:
        """Return the multiplier for an intersection of two wall types."""
        # Override types dominate
        if a == WallType.SHEAR_WALL or b == WallType.SHEAR_WALL:
            return 1.2
        if a == WallType.FACADE or b == WallType.FACADE:
            return 1.1
        # Symmetric lookup
        key = (a, b)
        if key in _WALL_TYPE_MULTIPLIERS:
            return _WALL_TYPE_MULTIPLIERS[key]
        rev = (b, a)
        if rev in _WALL_TYPE_MULTIPLIERS:
            return _WALL_TYPE_MULTIPLIERS[rev]
        return 1.0

    @staticmethod
    def _wall_near_point(w: _WallLine, x: float, y: float) -> bool:
        """True if point (x, y) is within INTERSECTION_PROXIMITY_MM of the wall line."""
        ax, ay = w.start
        bx, by = w.end
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 == 0:
            return math.hypot(x - ax, y - ay) <= INTERSECTION_PROXIMITY_MM
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        cx, cy = ax + t * dx, ay + t * dy
        return math.hypot(x - cx, y - cy) <= INTERSECTION_PROXIMITY_MM

    # ------------------------------------------------------------------
    # Cores
    # ------------------------------------------------------------------

    def identify_cores(
        self,
        grid: GridSystem,
        rooms: list[Room] | None = None,
        walls: list[WallSegment] | None = None,
    ) -> list[Core]:
        rooms = rooms or []
        core_rooms = [r for r in rooms if r.type in _CORE_ROOM_TYPES]
        if not core_rooms:
            return []

        has_stairs = any(r.type == RoomType.STAIRWELL for r in core_rooms)
        has_elevator = any(r.type == RoomType.ELEVATOR for r in core_rooms)

        xs: list[float] = []
        ys: list[float] = []
        stories: set[str] = set()
        for r in core_rooms:
            for pt in r.polygon:
                xs.append(pt[0])
                ys.append(pt[1])
            stories.add(r.story)

        polygon = [
            [min(xs), min(ys)],
            [max(xs), min(ys)],
            [max(xs), max(ys)],
            [min(xs), max(ys)],
            [min(xs), min(ys)],
        ]

        if has_stairs and has_elevator:
            core_type = CoreType.ELEVATOR_STAIR
        elif has_stairs:
            core_type = CoreType.STAIR_ONLY
        elif has_elevator:
            core_type = CoreType.ELEVATOR_ONLY
        else:
            core_type = CoreType.SERVICE

        core = Core(
            id="core-1",
            type=core_type,
            polygon=polygon,
            contains_elevator=has_elevator,
            contains_stairs=has_stairs,
            stories=sorted(stories),
        )
        logger.info("cores_identified", count=1, type=core_type.value)
        return [core]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _point_in_rect(x: float, y: float, rect: dict) -> bool:
        return (
            rect.get("x_min", 0) <= x <= rect.get("x_max", 0)
            and rect.get("y_min", 0) <= y <= rect.get("y_max", 0)
        )
