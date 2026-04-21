"""Step 9 — Corner resolution pass.

After snapping, walls are axis-aligned and endpoints that should
coincide have been welded.  What remains are *near-misses* — endpoints
that sit near another wall but do not quite touch it.  These almost
always represent intended joints (L, T, +) where the vectoriser lost
a few pixels at the intersection.

This pass does three things:

1. **Stub drop** — segments shorter than :attr:`CornerConfig.stub_wall_mm`
   are removed.  They are almost always vectoriser noise or the
   remains of a wall whose endpoints welded onto the same cluster.

2. **Endpoint-to-wall extension** — for each dangling endpoint within
   :attr:`CornerConfig.junction_radius_mm` of another wall's interior,
   extend (or clip) the endpoint to lie on that wall.  This fixes the
   T-junction case where the stem misses the crossbar by a few
   millimetres.

3. **Perpendicular endpoint-to-endpoint clip** — two endpoints that
   are within :attr:`CornerConfig.junction_radius_mm` and belong to
   walls at 90° get welded to the intersection of the two infinite
   lines.  Fixes the L-junction case where neither wall reaches the
   corner.

Moves are bounded by :attr:`CornerConfig.max_endpoint_shift_mm` so a
mis-snapped endpoint cannot pull distant walls together.  Walls keep
their IDs; dropped stubs are gone from the output entirely.
"""

from __future__ import annotations

from typing import Iterable, Optional

import structlog

from src.schema.building_graph import WallSegment

from .config import CornerConfig
from .primitives import (
    _FLOAT_EPSILON,
    _Seg,
    point_distance,
)

logger = structlog.get_logger(__name__)


def resolve_corners(
    walls: Iterable[WallSegment],
    config: CornerConfig,
) -> list[WallSegment]:
    """Public API: resolve junctions in *walls* per *config*.

    Returns a fresh list of schema :class:`WallSegment` instances with
    stubs dropped and endpoints extended to meet their neighbours.
    """

    segs = [_Seg.from_schema(w) for w in walls]
    if not segs:
        return []

    segs = _drop_stubs(segs, config.stub_wall_mm)
    # Order matters: the perpendicular clip runs *first* so L-junctions
    # where both walls fall short of the corner are snapped to their
    # true infinite-line intersection.  If we ran the endpoint-to-wall
    # extension first, each endpoint would get clamped to the nearest
    # vertex of the other wall — which is near the corner but not on
    # it, so the extension's own fixed point becomes the joint.
    _clip_perpendicular_pairs(
        segs,
        junction_radius=config.junction_radius_mm,
        max_shift=config.max_endpoint_shift_mm,
    )
    _extend_endpoints_to_walls(
        segs,
        junction_radius=config.junction_radius_mm,
        max_shift=config.max_endpoint_shift_mm,
    )
    # A second stub drop — extensions can collapse a short wall onto a
    # single point, and we don't want those leaking out.
    segs = _drop_stubs(segs, config.stub_wall_mm)

    return [s.to_schema() for s in segs]


# ---------------------------------------------------------------------------
# Stub removal
# ---------------------------------------------------------------------------


def _drop_stubs(segs: list[_Seg], stub_wall_mm: float) -> list[_Seg]:
    kept: list[_Seg] = []
    dropped = 0
    for s in segs:
        if s.length_mm >= stub_wall_mm - _FLOAT_EPSILON:
            kept.append(s)
        else:
            dropped += 1
    if dropped:
        logger.info("geometry_corners_stub_dropped", count=dropped)
    return kept


# ---------------------------------------------------------------------------
# Endpoint → wall extension (T-junctions, missed L-junctions with a long stem)
# ---------------------------------------------------------------------------


def _extend_endpoints_to_walls(
    segs: list[_Seg],
    *,
    junction_radius: float,
    max_shift: float,
) -> None:
    """For each dangling endpoint, extend it onto any nearby wall.

    "Nearby" means the perpendicular distance from the endpoint to the
    wall's infinite line is within *junction_radius*, AND the foot of
    the perpendicular falls within the wall's extent (plus a small
    junction-radius slack so endpoints just past a wall end still
    attach).
    """

    extended = 0
    # Snapshot endpoints before we start mutating — we iterate over
    # the original set so the extension order is deterministic.
    tasks: list[tuple[int, int]] = []  # (seg_index, role 0=start or 1=end)
    for si in range(len(segs)):
        tasks.append((si, 0))
        tasks.append((si, 1))

    for si, role in tasks:
        seg = segs[si]
        point = seg.start if role == 0 else seg.end

        best: Optional[tuple[float, int, float, float]] = None  # (dist, other_idx, fx, fy)
        for oi, other in enumerate(segs):
            if oi == si:
                continue
            proj = _project_onto_segment(point, other, slack=junction_radius)
            if proj is None:
                continue
            fx, fy, dist = proj
            if dist > junction_radius:
                continue
            if best is None or dist < best[0]:
                best = (dist, oi, fx, fy)

        if best is None:
            continue
        _dist, _oi, fx, fy = best

        # Bound the shift so distant corners don't get pulled together.
        if point_distance(point, [fx, fy]) > max_shift:
            continue

        if role == 0:
            seg.start = [fx, fy]
        else:
            seg.end = [fx, fy]
        seg.invalidate()
        extended += 1

    if extended:
        logger.info("geometry_corners_extended", count=extended)


def _project_onto_segment(
    point: list[float],
    seg: _Seg,
    *,
    slack: float,
) -> Optional[tuple[float, float, float]]:
    """Orthogonal projection of *point* onto *seg*'s line, clipped.

    Returns ``(foot_x, foot_y, distance)`` if the foot of the
    perpendicular lies within the segment's extent (plus *slack* past
    each end).  Returns ``None`` if the point projects past the ends
    of the segment by more than *slack* — i.e. the point is not
    adjacent to the wall at all.
    """

    ax, ay = seg.start
    bx, by = seg.end
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < _FLOAT_EPSILON:
        return None

    # Parameter t of the foot along [0, 1] between start and end.
    t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / length_sq
    # Allow slight overshoot on each side so an endpoint just past a
    # wall's end still attaches.
    length = length_sq**0.5
    slack_t = slack / length if length > 0 else 0.0
    if t < -slack_t or t > 1.0 + slack_t:
        return None

    # Clip t into the segment's true interior before computing the foot.
    # If t is in (-slack_t, 0) we treat it as touching the start vertex.
    t_clipped = max(0.0, min(1.0, t))
    fx = ax + t_clipped * dx
    fy = ay + t_clipped * dy
    distance = ((point[0] - fx) ** 2 + (point[1] - fy) ** 2) ** 0.5
    return fx, fy, distance


# ---------------------------------------------------------------------------
# Perpendicular endpoint-to-endpoint clip (missed L-junctions where both
# walls fall short of the corner)
# ---------------------------------------------------------------------------


def _clip_perpendicular_pairs(
    segs: list[_Seg],
    *,
    junction_radius: float,
    max_shift: float,
) -> None:
    """Pull the closer endpoints of two near-perpendicular walls to their
    shared infinite-line intersection."""

    clipped = 0
    pairs = _find_dangling_perpendicular_pairs(
        segs, tolerance=junction_radius
    )
    for (i, role_i), (j, role_j) in pairs:
        si = segs[i]
        sj = segs[j]
        ipt = si.start if role_i == 0 else si.end
        jpt = sj.start if role_j == 0 else sj.end

        intersection = _infinite_line_intersection(si, sj)
        if intersection is None:
            continue

        # Skip if either endpoint would travel further than max_shift.
        if point_distance(ipt, intersection) > max_shift:
            continue
        if point_distance(jpt, intersection) > max_shift:
            continue

        if role_i == 0:
            si.start = list(intersection)
        else:
            si.end = list(intersection)
        si.invalidate()

        if role_j == 0:
            sj.start = list(intersection)
        else:
            sj.end = list(intersection)
        sj.invalidate()
        clipped += 1

    if clipped:
        logger.info("geometry_corners_clipped_perpendicular", count=clipped)


def _find_dangling_perpendicular_pairs(
    segs: list[_Seg],
    *,
    tolerance: float,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    tol_sq = tolerance * tolerance
    for i in range(len(segs)):
        for role_i in (0, 1):
            for j in range(i + 1, len(segs)):
                # Only consider walls that are near-perpendicular.
                if not _is_near_perpendicular(segs[i], segs[j]):
                    continue
                for role_j in (0, 1):
                    ipt = segs[i].start if role_i == 0 else segs[i].end
                    jpt = segs[j].start if role_j == 0 else segs[j].end
                    dx = ipt[0] - jpt[0]
                    dy = ipt[1] - jpt[1]
                    if dx * dx + dy * dy <= tol_sq:
                        # If the endpoints are already the same vertex,
                        # nothing to do — skip.
                        if dx * dx + dy * dy < _FLOAT_EPSILON:
                            continue
                        pairs.append(((i, role_i), (j, role_j)))
    return pairs


def _is_near_perpendicular(a: _Seg, b: _Seg) -> bool:
    """True if *a* and *b* differ by ~90° in the canonical [0, 180) range."""

    diff = abs(a.angle_deg - b.angle_deg)
    return abs(diff - 90.0) < 10.0


def _infinite_line_intersection(
    a: _Seg, b: _Seg
) -> Optional[tuple[float, float]]:
    """Intersection of the two infinite lines through *a* and *b*.

    Returns ``None`` if the lines are parallel (determinant near zero).
    """

    ax1, ay1 = a.start
    ax2, ay2 = a.end
    bx1, by1 = b.start
    bx2, by2 = b.end
    adx = ax2 - ax1
    ady = ay2 - ay1
    bdx = bx2 - bx1
    bdy = by2 - by1
    denom = adx * bdy - ady * bdx
    if abs(denom) < _FLOAT_EPSILON:
        return None
    t = ((bx1 - ax1) * bdy - (by1 - ay1) * bdx) / denom
    return ax1 + t * adx, ay1 + t * ady


__all__ = ["resolve_corners"]
