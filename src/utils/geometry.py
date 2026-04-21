"""Shared geometry utilities built on Shapely.

All coordinates in millimeters unless noted otherwise.
"""

from __future__ import annotations

import math
from typing import Sequence

from shapely.geometry import LineString, Point, Polygon


def distance_2d(p1: Sequence[float], p2: Sequence[float]) -> float:
    """Euclidean distance between two 2-D points."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def polygon_area_mm2(pts: list[list[float]]) -> float:
    """Signed area of a 2-D polygon (Shoelace formula) in mm²."""
    poly = Polygon(pts)
    return abs(poly.area)


def polygon_area_m2(pts: list[list[float]]) -> float:
    """Area in m² from mm-coordinate polygon."""
    return polygon_area_mm2(pts) / 1_000_000


def polygon_perimeter_mm(pts: list[list[float]]) -> float:
    """Perimeter of a 2-D polygon in mm."""
    poly = Polygon(pts)
    return poly.length


def close_polygon(pts: list[list[float]]) -> list[list[float]]:
    """Ensure the polygon is closed (first point == last point)."""
    if not pts:
        return pts
    if pts[0] != pts[-1]:
        return pts + [pts[0]]
    return pts


def line_angle_degrees(start: Sequence[float], end: Sequence[float]) -> float:
    """Angle of a line segment in degrees [0, 180)."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.degrees(math.atan2(dy, dx)) % 180
    return angle


def snap_angle(angle_deg: float, tolerance_deg: float = 3.0) -> float:
    """Snap an angle to the nearest canonical direction (0, 45, 90, 135)."""
    canonical = [0, 45, 90, 135, 180]
    for ca in canonical:
        if abs(angle_deg - ca) <= tolerance_deg:
            return ca % 180
    return angle_deg


def segments_collinear(
    seg1_start: Sequence[float],
    seg1_end: Sequence[float],
    seg2_start: Sequence[float],
    seg2_end: Sequence[float],
    angle_tol_deg: float = 5.0,
    dist_tol_mm: float = 100.0,
) -> bool:
    """Check whether two line segments are roughly collinear.

    Uses the perpendicular distance from seg2's midpoint to the *infinite*
    line through seg1 (not the finite segment).
    """
    a1 = line_angle_degrees(seg1_start, seg1_end)
    a2 = line_angle_degrees(seg2_start, seg2_end)
    angle_diff = min(abs(a1 - a2), 180 - abs(a1 - a2))
    if angle_diff > angle_tol_deg:
        return False
    # Perpendicular distance from seg2's midpoint to the infinite line of seg1
    mid2 = [(seg2_start[0] + seg2_end[0]) / 2, (seg2_start[1] + seg2_end[1]) / 2]
    perp_dist = _point_to_line_distance(mid2, seg1_start, seg1_end)
    return perp_dist <= dist_tol_mm


def _point_to_line_distance(
    pt: Sequence[float], line_start: Sequence[float], line_end: Sequence[float]
) -> float:
    """Perpendicular distance from *pt* to the infinite line through two points."""
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(pt[0] - line_start[0], pt[1] - line_start[1])
    return abs(dy * pt[0] - dx * pt[1] + line_end[0] * line_start[1] - line_end[1] * line_start[0]) / length


def rectangular_polygon_mm(
    x_start: float, y_start: float, x_end: float, y_end: float
) -> list[list[float]]:
    """Create a closed rectangular polygon from two corners."""
    return [
        [x_start, y_start],
        [x_end, y_start],
        [x_end, y_end],
        [x_start, y_end],
        [x_start, y_start],
    ]
