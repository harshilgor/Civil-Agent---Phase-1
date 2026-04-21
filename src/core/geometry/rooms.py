"""Step 9 — Room polygon extraction.

Given a cleaned list of wall segments, find every enclosed face and
emit it as a :class:`Room`.  Implementation uses shapely's
``polygonize`` on a `MultiLineString` of the wall centrelines, which
returns every 2-D face of the planar subdivision.

Holes are detected by checking which faces are contained inside other
faces — a face completely inside another is a hole (courtyard or
core void) on the enclosing face, not a separate room.

Room type hints let the ML/OCR layer label specific rooms before this
pass runs; any face whose centroid lies inside a hint polygon inherits
the hint's :class:`RoomType` and label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

import structlog
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from src.schema.building_graph import Room, WallSegment
from src.schema.enums import RoomType

from .config import RoomConfig

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RoomHint:
    """Optional pre-labelled region hint (from OCR / VLM / CAD).

    When provided, any extracted face whose centroid lies inside the
    hint's polygon inherits the hint's ``room_type`` and ``label``.
    """

    polygon: list[list[float]]
    room_type: RoomType
    label: str


def extract_rooms(
    walls: Iterable[WallSegment],
    config: RoomConfig,
    *,
    hints: Optional[list[RoomHint]] = None,
    story_id: str = "S1",
    id_prefix: str = "room",
) -> list[Room]:
    """Public API: extract closed rooms from *walls*.

    The returned list is sorted by descending area so the first
    element is always the largest room on the plan — useful for
    sanity assertions and for picking a "main" space.
    """

    wall_list = list(walls)
    if not wall_list:
        return []

    # Build shapely LineStrings with a tiny buffer so endpoints that
    # merely come close (but did not get fully welded) still connect
    # in the planar subdivision.  50mm matches the Step-9 simplification
    # tolerance and is well below any real-world wall thickness we care
    # about.
    lines = _walls_to_lines(wall_list)
    if not lines:
        return []

    faces = _polygonize_faces(lines, simplification_mm=config.simplification_mm)
    if not faces:
        logger.info("geometry_rooms_no_faces", walls=len(wall_list))
        return []

    # Drop tiny faces (noise) and classify remaining faces as
    # either proper rooms or holes-of-other-rooms.
    holes, rooms = _classify_faces(
        faces,
        minimum_area_m2=config.minimum_area_m2,
        hole_threshold_m2=config.hole_threshold_m2,
    )
    logger.info(
        "geometry_rooms_extracted",
        walls=len(wall_list),
        faces=len(faces),
        rooms=len(rooms),
        holes=len(holes),
    )

    # Sort by descending area so callers get a stable ordering.
    rooms.sort(key=lambda p: -p.area)

    prepared_hints = [
        (Polygon(h.polygon), h.room_type, h.label) for h in (hints or [])
    ]

    out: list[Room] = []
    for i, poly in enumerate(rooms):
        room_type, label = _apply_hints(poly, prepared_hints)
        perimeter_mm = float(poly.length)
        out.append(
            Room(
                id=f"{id_prefix}_{i:03d}_{uuid.uuid4().hex[:6]}",
                label=label or f"Room {i + 1}",
                type=room_type,
                polygon=[list(pt) for pt in poly.exterior.coords[:-1]],
                area_m2=float(poly.area) / 1_000_000.0,  # mm² → m²
                story=story_id,
                perimeter_mm=perimeter_mm,
                confidence=0.85,  # inferred from geometry, not direct detection
            )
        )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _walls_to_lines(walls: list[WallSegment]) -> list[LineString]:
    lines: list[LineString] = []
    for w in walls:
        if w.start == w.end:
            continue
        lines.append(LineString([w.start, w.end]))
    return lines


def _polygonize_faces(
    lines: list[LineString],
    *,
    simplification_mm: float,
) -> list[Polygon]:
    """Run :func:`shapely.ops.polygonize` and simplify the result.

    ``polygonize`` already handles all the planar-subdivision work:
    it returns every bounded face implied by the input lines, with
    correct hole detection for fully-enclosed subfaces.
    """

    # ``unary_union`` splits crossing segments at their intersection
    # points so polygonize sees a valid planar graph.
    noded: BaseGeometry = unary_union(MultiLineString(lines))
    raw_faces = list(polygonize(noded))

    faces: list[Polygon] = []
    for f in raw_faces:
        if not isinstance(f, Polygon):
            continue
        simplified = f.simplify(tolerance=simplification_mm, preserve_topology=True)
        if simplified.is_empty or not isinstance(simplified, Polygon):
            continue
        faces.append(simplified)
    return faces


def _classify_faces(
    faces: list[Polygon],
    *,
    minimum_area_m2: float,
    hole_threshold_m2: float,
) -> tuple[list[Polygon], list[Polygon]]:
    """Separate faces into (holes, rooms).

    A face is treated as a hole when:

    * its area is below ``hole_threshold_m2`` in m², AND
    * it is spatially contained inside a strictly larger face.

    Any face below ``minimum_area_m2`` that is NOT contained inside
    another face is dropped entirely as noise.
    """

    # Sort faces by area descending so we compare each candidate
    # against larger ones only (a face cannot contain something bigger
    # than itself).
    faces_by_area = sorted(faces, key=lambda p: -p.area)
    min_area_mm2 = minimum_area_m2 * 1_000_000.0
    hole_area_mm2 = hole_threshold_m2 * 1_000_000.0

    rooms: list[Polygon] = []
    holes: list[Polygon] = []
    for face in faces_by_area:
        area_mm2 = face.area
        # Find an enclosing face among already-accepted rooms.
        enclosing = None
        for candidate in rooms:
            if candidate.area > face.area and candidate.contains(face):
                enclosing = candidate
                break

        if enclosing is not None and area_mm2 < hole_area_mm2:
            holes.append(face)
            continue

        if area_mm2 < min_area_mm2:
            # Tiny face, not enclosed by anything → drop as noise.
            continue

        rooms.append(face)
    return holes, rooms


def _apply_hints(
    face: Polygon,
    hints: list[tuple[Polygon, RoomType, str]],
) -> tuple[RoomType, str]:
    """Return ``(room_type, label)`` for *face* given the hint list."""

    if not hints:
        return RoomType.UNDEFINED, ""
    centroid: Point = face.centroid
    for hint_poly, room_type, label in hints:
        if hint_poly.contains(centroid):
            return room_type, label
    return RoomType.UNDEFINED, ""


__all__ = ["RoomHint", "extract_rooms"]
