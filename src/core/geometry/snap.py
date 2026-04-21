"""Step 9 — Orthogonal snapping pass.

Takes a list of wall segments and returns a list where:

* Walls within :attr:`SnapConfig.angular_tolerance_deg` of a cardinal
  axis are rotated to that axis in-place (endpoints repositioned so
  the segment is truly axis-aligned — not just "close enough").
* Vertical and horizontal walls whose X / Y coordinates fall within
  :attr:`SnapConfig.axis_cluster_mm` are welded to a common rail.
* Individual endpoints (not whole segments) within
  :attr:`SnapConfig.endpoint_weld_mm` of each other collapse to a
  single point — this is what gets T- and L-junctions to actually
  share a vertex instead of approximately-sharing one.

Diagonal walls are preserved when ``preserve_diagonals`` is True.
Everything here operates on :class:`_Seg` instances; the public API
converts from and to schema :class:`WallSegment`.
"""

from __future__ import annotations

from typing import Iterable

import structlog

from src.schema.building_graph import WallSegment

from .config import SnapConfig
from .primitives import (
    _Seg,
    angular_distance_deg,
    cluster_1d,
    is_orthogonal,
    nearest_orthogonal_axis_deg,
    point_distance,
)

logger = structlog.get_logger(__name__)


def snap_orthogonal(
    walls: Iterable[WallSegment],
    config: SnapConfig,
) -> list[WallSegment]:
    """Public API: snap *walls* per *config* and return the result.

    The input is not mutated — each returned :class:`WallSegment` is a
    freshly constructed pydantic model.
    """

    segs = [_Seg.from_schema(w) for w in walls]
    if not segs:
        return []

    _snap_segments(segs, config)
    return [s.to_schema() for s in segs]


# ---------------------------------------------------------------------------
# Internal helpers.  These mutate *segs* in place — the public wrapper
# above handles the copy-in / copy-out.
# ---------------------------------------------------------------------------


def _snap_segments(segs: list[_Seg], config: SnapConfig) -> None:
    """Three-phase snap: angle snap → axis clustering → endpoint weld."""

    # 1) Angle snap.  Walls within angular tolerance of an axis are
    #    rotated to that axis by moving only the shorter half to the
    #    longer half's X (for horizontal) or Y (for vertical).  Using
    #    the midpoint is tempting but biases the line; anchoring on
    #    the longer end preserves the dominant geometry.
    rotated = 0
    for seg in segs:
        if not is_orthogonal(seg, config.angular_tolerance_deg):
            if config.preserve_diagonals:
                continue
            # If diagonals are NOT preserved, still pick the nearer axis.
        axis = nearest_orthogonal_axis_deg(seg.angle_deg)
        if _align_to_axis(seg, axis):
            rotated += 1

    # 2) Axis clustering.  Now every orthogonal wall is truly axis-
    #    aligned.  Group vertical walls by X and horizontal walls by Y;
    #    collapse each cluster onto a single rail.  Weight by wall
    #    length so short walls don't drag long ones off their rail.
    vertical_segs = [s for s in segs if _is_vertical(s)]
    horizontal_segs = [s for s in segs if _is_horizontal(s)]

    _cluster_along_axis(
        vertical_segs,
        coord="x",
        tolerance=config.axis_cluster_mm,
    )
    _cluster_along_axis(
        horizontal_segs,
        coord="y",
        tolerance=config.axis_cluster_mm,
    )

    # 3) Endpoint weld.  Snap individual endpoints that are within
    #    endpoint_weld_mm of each other.  Separate from axis
    #    clustering because two walls can share a rail (both on X=4000)
    #    but have different Y endpoints — the endpoint weld catches
    #    those as joints.
    welded = _weld_endpoints(segs, tolerance=config.endpoint_weld_mm)

    logger.info(
        "geometry_snap_complete",
        total=len(segs),
        angle_snapped=rotated,
        vertical=len(vertical_segs),
        horizontal=len(horizontal_segs),
        endpoints_welded=welded,
    )


def _align_to_axis(seg: _Seg, axis_deg: float) -> bool:
    """Mutate *seg* so its endpoints lie on an axis-aligned line.

    Returns True if the segment was actually rotated (i.e. it wasn't
    already perfectly on the axis).
    """

    sx, sy = seg.start
    ex, ey = seg.end
    if axis_deg == 0.0:
        # Horizontal line — unify Y on both endpoints.  Use the longer
        # half's Y to anchor.  With only two points the "longer half"
        # is whichever has the Y closer to the midline — we take the
        # weighted midpoint (simple mean), which is adequate given
        # angular tolerance is already small (≤ 5°).
        target_y = (sy + ey) / 2.0
        moved = abs(sy - target_y) > 0.0 or abs(ey - target_y) > 0.0
        seg.start[1] = target_y
        seg.end[1] = target_y
    else:  # 90°
        target_x = (sx + ex) / 2.0
        moved = abs(sx - target_x) > 0.0 or abs(ex - target_x) > 0.0
        seg.start[0] = target_x
        seg.end[0] = target_x
    seg.invalidate()
    return moved


def _is_vertical(seg: _Seg) -> bool:
    # Post-alignment: a vertical wall has identical X on both endpoints.
    # Use a tiny epsilon to survive floating-point noise from alignment.
    return abs(seg.start[0] - seg.end[0]) <= 1e-3 and seg.length_mm > 1e-6


def _is_horizontal(seg: _Seg) -> bool:
    return abs(seg.start[1] - seg.end[1]) <= 1e-3 and seg.length_mm > 1e-6


def _cluster_along_axis(
    segs: list[_Seg],
    *,
    coord: str,
    tolerance: float,
) -> None:
    """Cluster *segs* along the given ``coord`` axis (``'x'`` or ``'y'``).

    Coordinate is the one shared by both endpoints for an orthogonal
    wall — X for vertical walls, Y for horizontal walls.  Clusters
    within *tolerance* collapse to their length-weighted mean.
    """

    if not segs:
        return

    idx = 0 if coord == "x" else 1
    values = [s.start[idx] for s in segs]
    weights = [s.length_mm for s in segs]
    clusters = cluster_1d(values, tolerance, weights=weights)

    for center, members in clusters:
        if len(members) < 2:
            continue  # Solo walls on their own rail are left alone.
        for mi in members:
            s = segs[mi]
            s.start[idx] = center
            s.end[idx] = center
            s.invalidate()


def _weld_endpoints(segs: list[_Seg], tolerance: float) -> int:
    """Snap close endpoints to a common point.

    Collects every endpoint, clusters them pair-wise by proximity, and
    rewrites each cluster member to the cluster center.  Returns the
    number of endpoints that actually moved.
    """

    if not segs:
        return 0

    endpoints: list[tuple[int, int, float, float]] = []
    for si, seg in enumerate(segs):
        endpoints.append((si, 0, seg.start[0], seg.start[1]))
        endpoints.append((si, 1, seg.end[0], seg.end[1]))

    # Simple O(n²) neighbour lookup is fine at Phase-1 plan scale
    # (hundreds of walls at most).  If this ever becomes a bottleneck,
    # switch to a KD-tree from scipy.spatial.
    parent = list(range(len(endpoints)))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i: int, j: int) -> None:
        ri, rj = _find(i), _find(j)
        if ri != rj:
            parent[rj] = ri

    tol_sq = tolerance * tolerance
    for i in range(len(endpoints)):
        _, _, xi, yi = endpoints[i]
        for j in range(i + 1, len(endpoints)):
            _, _, xj, yj = endpoints[j]
            dx = xi - xj
            dy = yi - yj
            if dx * dx + dy * dy <= tol_sq:
                _union(i, j)

    # Compute cluster centers and rewrite.
    groups: dict[int, list[int]] = {}
    for i in range(len(endpoints)):
        groups.setdefault(_find(i), []).append(i)

    moved = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        cx = sum(endpoints[m][2] for m in members) / len(members)
        cy = sum(endpoints[m][3] for m in members) / len(members)
        for m in members:
            si, role, x0, y0 = endpoints[m]
            seg = segs[si]
            old = seg.start if role == 0 else seg.end
            if point_distance(old, [cx, cy]) > 0.0:
                moved += 1
            if role == 0:
                seg.start = [cx, cy]
            else:
                seg.end = [cx, cy]
            seg.invalidate()

    # A wall whose endpoints welded onto the same point becomes a
    # degenerate zero-length segment.  Those get dropped by the corner
    # pass' stub-wall filter; we leave them here for the snap to stay
    # a pure geometric transformation.
    return moved


__all__ = ["snap_orthogonal"]
