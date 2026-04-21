"""Internal dataclasses and vector helpers used across geometry passes.

These types are NOT part of the public BuildingGraph schema — they are
mutable, simple, and tuned for fast geometric computation.  Every pass
takes schema models in and gives schema models out; these primitives
live only between passes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from src.schema.building_graph import WallSegment
from src.schema.enums import WallType
from src.schema.provenance import ProvenanceRecord

# ---------------------------------------------------------------------------
# Geometric tolerances used for internal comparisons.  These are NOT
# tuning knobs — they are numeric floors for float safety.
# ---------------------------------------------------------------------------

_FLOAT_EPSILON = 1e-6


# ---------------------------------------------------------------------------
# Internal segment representation
# ---------------------------------------------------------------------------


@dataclass
class _Seg:
    """Mutable wall segment used while passes rewrite geometry.

    Carries everything the schema :class:`WallSegment` carries, plus an
    ``angle_deg`` cache that is invalidated whenever the endpoints move
    (see :meth:`_Seg.invalidate`).
    """

    id: str
    type: WallType
    start: list[float]
    end: list[float]
    thickness_mm: float
    stories: list[str]
    height_mm: Optional[float] = None
    material: Optional[str] = None
    confidence: float = 1.0
    provenance: Optional[ProvenanceRecord] = None
    # Cache — populated lazily.
    _angle_deg: Optional[float] = field(default=None, repr=False, compare=False)
    _length_mm: Optional[float] = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Derived geometry
    # ------------------------------------------------------------------

    @property
    def length_mm(self) -> float:
        if self._length_mm is None:
            dx = self.end[0] - self.start[0]
            dy = self.end[1] - self.start[1]
            self._length_mm = math.hypot(dx, dy)
        return self._length_mm

    @property
    def angle_deg(self) -> float:
        """Angle in the closed interval ``[0, 180)``.

        Walls are undirected — a segment from (0,0) to (10,0) has the
        same angle as one from (10,0) to (0,0).  We collapse to
        ``[0, 180)`` so direction flips do not register as different
        orientations during axis clustering.
        """

        if self._angle_deg is None:
            dx = self.end[0] - self.start[0]
            dy = self.end[1] - self.start[1]
            if abs(dx) < _FLOAT_EPSILON and abs(dy) < _FLOAT_EPSILON:
                self._angle_deg = 0.0
            else:
                angle = math.degrees(math.atan2(dy, dx))
                # Collapse to [0, 180).
                while angle < 0.0:
                    angle += 180.0
                while angle >= 180.0:
                    angle -= 180.0
                self._angle_deg = angle
        return self._angle_deg

    def invalidate(self) -> None:
        """Drop cached angle/length after mutating an endpoint."""

        self._angle_deg = None
        self._length_mm = None

    # ------------------------------------------------------------------
    # Schema conversion
    # ------------------------------------------------------------------

    @classmethod
    def from_schema(cls, wall: WallSegment) -> "_Seg":
        return cls(
            id=wall.id,
            type=wall.type,
            start=[float(wall.start[0]), float(wall.start[1])],
            end=[float(wall.end[0]), float(wall.end[1])],
            thickness_mm=float(wall.thickness_mm),
            stories=list(wall.stories),
            height_mm=wall.height_mm,
            material=wall.material,
            confidence=float(wall.confidence),
            provenance=wall.provenance,
        )

    def to_schema(self) -> WallSegment:
        return WallSegment(
            id=self.id,
            type=self.type,
            start=list(self.start),
            end=list(self.end),
            thickness_mm=self.thickness_mm,
            height_mm=self.height_mm,
            stories=list(self.stories),
            material=self.material,
            confidence=self.confidence,
            provenance=self.provenance,
        )


# ---------------------------------------------------------------------------
# Vector helpers.  These are the only places trigonometry lives —
# everything above uses the cached ``_Seg`` properties.
# ---------------------------------------------------------------------------


def angular_distance_deg(a: float, b: float, *, period: float = 180.0) -> float:
    """Smallest absolute angular distance between *a* and *b*.

    Both are assumed to already live in ``[0, period)``; the result is
    in ``[0, period/2]``.  Useful for "is this wall close to an axis"
    questions where the axis angles are ``[0.0, 90.0]`` and we don't
    care which side of the axis we are on.
    """

    diff = abs(a - b) % period
    return min(diff, period - diff)


def nearest_orthogonal_axis_deg(angle_deg: float) -> float:
    """Return 0.0 or 90.0, whichever is closer to *angle_deg*.

    Expects ``angle_deg`` in ``[0, 180)`` — the canonical range used by
    :attr:`_Seg.angle_deg`.
    """

    to_zero = angular_distance_deg(angle_deg, 0.0)
    to_ninety = angular_distance_deg(angle_deg, 90.0)
    return 90.0 if to_ninety < to_zero else 0.0


def is_orthogonal(seg: _Seg, tolerance_deg: float) -> bool:
    """``True`` if the segment is within *tolerance_deg* of an axis."""

    a = seg.angle_deg
    return angular_distance_deg(a, 0.0) <= tolerance_deg or angular_distance_deg(
        a, 90.0
    ) <= tolerance_deg


def cluster_1d(
    values: list[float],
    tolerance: float,
    *,
    weights: Optional[list[float]] = None,
) -> list[tuple[float, list[int]]]:
    """Cluster 1-D *values* into groups, each spanning at most *tolerance*.

    Returns a list of ``(cluster_center, [indices into values])`` pairs,
    ordered by ascending center.  When *weights* is provided the
    cluster center is the weighted mean; otherwise it is the plain
    mean.  Useful for axis-clustering wall positions and endpoints.
    """

    if not values:
        return []

    idx_sorted = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[tuple[float, list[int]]] = []
    current_members: list[int] = []
    current_values: list[float] = []
    current_min = math.inf
    current_max = -math.inf

    for i in idx_sorted:
        v = values[i]
        # A new value joins the current cluster only if the span would
        # still fit inside `tolerance` — this is stricter than simple
        # "gap < tolerance" and prevents a chain of overlapping pairs
        # from collapsing into an oversized cluster.
        new_min = min(current_min, v)
        new_max = max(current_max, v)
        if current_members and (new_max - new_min) > tolerance:
            clusters.append(_cluster_center(current_values, current_members, weights))
            current_members = []
            current_values = []
            current_min = math.inf
            current_max = -math.inf
            new_min = v
            new_max = v
        current_members.append(i)
        current_values.append(v)
        current_min = new_min
        current_max = new_max

    if current_members:
        clusters.append(_cluster_center(current_values, current_members, weights))

    return clusters


def _cluster_center(
    values: list[float],
    members: list[int],
    weights: Optional[list[float]],
) -> tuple[float, list[int]]:
    if weights is None:
        center = sum(values) / len(values)
    else:
        w = [weights[i] for i in members]
        wsum = sum(w)
        if wsum <= _FLOAT_EPSILON:
            center = sum(values) / len(values)
        else:
            center = sum(v * wi for v, wi in zip(values, w)) / wsum
    return center, list(members)


def segment_bounds(seg: _Seg) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box (xmin, ymin, xmax, ymax) of the segment."""

    xmin = min(seg.start[0], seg.end[0])
    ymin = min(seg.start[1], seg.end[1])
    xmax = max(seg.start[0], seg.end[0])
    ymax = max(seg.start[1], seg.end[1])
    return xmin, ymin, xmax, ymax


def point_distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


__all__ = [
    "_FLOAT_EPSILON",
    "_Seg",
    "angular_distance_deg",
    "cluster_1d",
    "is_orthogonal",
    "nearest_orthogonal_axis_deg",
    "point_distance",
    "segment_bounds",
]
