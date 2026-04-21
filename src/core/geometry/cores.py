"""Step 9 — Vertical-core detection.

Given the list of rooms emitted by :mod:`rooms`, find contiguous
clusters of service rooms (stair / elevator / toilet / MEP) and emit
each cluster as a :class:`Core`.  "Contiguous" means the bounding
boxes touch or overlap within
:attr:`CoreConfig.adjacency_tolerance_mm` — a stud-wall thickness.

The core polygon is the convex hull of the union of member-room
polygons.  A convex hull is a deliberate simplification: real cores
are often rectangular or L-shaped, but at Phase-1 the downstream
structural model only cares about the planar *footprint* for vertical
continuity — a convex wrap captures that without over-committing to
the detailed geometry.
"""

from __future__ import annotations

import uuid
from typing import Iterable

import structlog
from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.schema.building_graph import Core, Room
from src.schema.enums import CoreType, RoomType

from .config import CoreConfig

logger = structlog.get_logger(__name__)


# No direct 1:1 mapping: CoreType captures combinations
# (ELEVATOR_STAIR, STAIR_ONLY, ELEVATOR_ONLY, SERVICE, MEP), so we infer
# the cluster type from *which seed room types are present* instead of
# from a per-room type.  See :func:`_infer_core_type`.


def detect_cores(
    rooms: Iterable[Room],
    config: CoreConfig,
    *,
    id_prefix: str = "core",
) -> list[Core]:
    """Public API: cluster service rooms into cores.

    Returns a list sorted by descending area so the largest core is
    always ``out[0]`` — convenient for "main vertical circulation"
    heuristics in later stages.
    """

    seeds = [r for r in rooms if r.type in config.seed_room_types]
    if not seeds:
        return []

    clusters = _cluster_seeds(seeds, config.adjacency_tolerance_mm)
    min_area_mm2 = config.minimum_cluster_area_m2 * 1_000_000.0

    out: list[Core] = []
    for cluster in clusters:
        polygon, dominant_type, flags = _build_cluster_polygon(
            cluster, simplification_mm=config.simplification_mm
        )
        if polygon is None or polygon.area < min_area_mm2:
            continue

        stories = sorted({r.story for r in cluster})
        out.append(
            Core(
                id=f"{id_prefix}_{uuid.uuid4().hex[:8]}",
                type=dominant_type,
                polygon=[list(pt) for pt in polygon.exterior.coords[:-1]],
                contains_elevator=flags["contains_elevator"],
                contains_stairs=flags["contains_stairs"],
                stories=stories,
                confidence=0.75,
            )
        )

    out.sort(key=lambda c: -_polygon_area_mm2(c.polygon))
    logger.info(
        "geometry_cores_detected",
        seed_rooms=len(seeds),
        clusters=len(clusters),
        emitted=len(out),
    )
    return out


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def _cluster_seeds(
    seeds: list[Room], adjacency_tolerance_mm: float
) -> list[list[Room]]:
    """Union-find over seeds whose bounding boxes are within tolerance."""

    n = len(seeds)
    parent = list(range(n))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i: int, j: int) -> None:
        ri, rj = _find(i), _find(j)
        if ri != rj:
            parent[rj] = ri

    bboxes = [_room_bbox(r) for r in seeds]
    for i in range(n):
        for j in range(i + 1, n):
            if _bboxes_adjacent(bboxes[i], bboxes[j], adjacency_tolerance_mm):
                _union(i, j)

    groups: dict[int, list[Room]] = {}
    for i in range(n):
        groups.setdefault(_find(i), []).append(seeds[i])
    return list(groups.values())


def _room_bbox(room: Room) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in room.polygon]
    ys = [pt[1] for pt in room.polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def _bboxes_adjacent(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    tolerance: float,
) -> bool:
    """Axis-aligned bboxes touch / overlap within *tolerance* on both axes."""

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    x_overlap = max(ax1, bx1) <= min(ax2, bx2) + tolerance
    y_overlap = max(ay1, by1) <= min(ay2, by2) + tolerance
    return x_overlap and y_overlap


# ---------------------------------------------------------------------------
# Polygon assembly + type inference
# ---------------------------------------------------------------------------


def _build_cluster_polygon(
    cluster: list[Room],
    *,
    simplification_mm: float,
):
    polys = [Polygon(r.polygon) for r in cluster if len(r.polygon) >= 3]
    if not polys:
        return None, CoreType.SERVICE, {
            "contains_elevator": False,
            "contains_stairs": False,
        }

    union = unary_union(polys)
    hull = union.convex_hull

    if not isinstance(hull, Polygon):
        return None, CoreType.SERVICE, {
            "contains_elevator": False,
            "contains_stairs": False,
        }

    simplified = hull.simplify(tolerance=simplification_mm, preserve_topology=True)
    if not isinstance(simplified, Polygon) or simplified.is_empty:
        simplified = hull

    contains_elevator = any(r.type == RoomType.ELEVATOR for r in cluster)
    contains_stairs = any(r.type == RoomType.STAIRWELL for r in cluster)
    core_type = _infer_core_type(cluster)
    return simplified, core_type, {
        "contains_elevator": contains_elevator,
        "contains_stairs": contains_stairs,
    }


def _infer_core_type(cluster: list[Room]) -> CoreType:
    """Pick the :class:`CoreType` that best describes *cluster*.

    The enum is coarse — it encodes the common vertical-circulation
    pairings that structural engineers classify cores by.  Precedence:

    1. Both stair and elevator present → ``ELEVATOR_STAIR``.
    2. Stair only → ``STAIR_ONLY``.
    3. Elevator only → ``ELEVATOR_ONLY``.
    4. Only MEP rooms → ``MEP``.
    5. Everything else (toilets, mixed service spaces) → ``SERVICE``.
    """

    has_stair = any(r.type == RoomType.STAIRWELL for r in cluster)
    has_elevator = any(r.type == RoomType.ELEVATOR for r in cluster)
    all_mechanical = all(r.type == RoomType.MECHANICAL for r in cluster)

    if has_stair and has_elevator:
        return CoreType.ELEVATOR_STAIR
    if has_stair:
        return CoreType.STAIR_ONLY
    if has_elevator:
        return CoreType.ELEVATOR_ONLY
    if all_mechanical:
        return CoreType.MEP
    return CoreType.SERVICE


def _polygon_area_mm2(polygon: list[list[float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    return float(Polygon(polygon).area)


__all__ = ["detect_cores"]
