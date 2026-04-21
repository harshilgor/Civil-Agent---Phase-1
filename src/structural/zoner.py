"""Structural zoning.

Classifies regions of each story into ``StructuralZoneType`` labels that
describe their expected *structural behavior* (not just architectural use).
Examples: CORE_SERVICE, CORRIDOR_BAND, OPEN_FLOOR_PLATE, TRANSFER_RISK.
"""

from __future__ import annotations

import logging
from typing import Iterable

from shapely.geometry import Polygon

from src.schema.building_graph import BuildingGraph, Core, Room, Story
from src.schema.enums import RoomType
from src.schema.structural_enums import StructuralZoneType
from src.schema.structural_graph import StructuralZone
from src.structural.config import DEFAULT_CONFIG, StructuralConfig
from src.utils.geometry import polygon_area_m2

logger = logging.getLogger(__name__)


_SERVICE_ROOM_TYPES = {
    RoomType.STAIRWELL,
    RoomType.ELEVATOR,
    RoomType.MECHANICAL,
    RoomType.BATHROOM,
}

_OPEN_ROOM_TYPES = {
    RoomType.OFFICE,
    RoomType.CONFERENCE,
    RoomType.LIVING_ROOM,
    RoomType.UNDEFINED,
}


class StructuralZoner:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def classify(self, graph: BuildingGraph) -> list[StructuralZone]:
        zones: list[StructuralZone] = []
        story_by_id = {s.id: s for s in graph.stories}
        story_areas = {s.id: s.floor_area_gross_m2 for s in graph.stories}

        for story in graph.stories:
            zones.extend(self._core_zones(graph.cores, story))
            zones.extend(self._room_zones(graph.rooms, story))
            zones.extend(self._transfer_risk_zones(graph, story, story_areas))
        return zones

    # ------------------------------------------------------------------
    # Core zones (CORE_SERVICE)
    # ------------------------------------------------------------------

    def _core_zones(self, cores: Iterable[Core], story: Story) -> list[StructuralZone]:
        out = []
        for core in cores:
            if story.id not in core.stories and core.stories:
                continue
            poly = core.polygon
            area = polygon_area_m2(poly)
            out.append(
                StructuralZone(
                    id=f"zone-core-{core.id}-{story.id}",
                    type=StructuralZoneType.CORE_SERVICE,
                    polygon=poly,
                    story=story.id,
                    area_m2=area,
                    notes=f"Core {core.type.value}",
                )
            )
        return out

    # ------------------------------------------------------------------
    # Room-derived zones
    # ------------------------------------------------------------------

    def _room_zones(self, rooms: Iterable[Room], story: Story) -> list[StructuralZone]:
        out = []
        for room in rooms:
            if room.story != story.id:
                continue

            zone_type = self._classify_room(room)
            if zone_type is None:
                continue

            out.append(
                StructuralZone(
                    id=f"zone-room-{room.id}",
                    type=zone_type,
                    polygon=room.polygon,
                    story=story.id,
                    area_m2=room.area_m2,
                    notes=f"Room {room.label} ({room.type.value})",
                )
            )
        return out

    def _classify_room(self, room: Room) -> StructuralZoneType | None:
        cfg = self.config.zoning

        if room.type in _SERVICE_ROOM_TYPES:
            return StructuralZoneType.CORE_SERVICE

        if room.type == RoomType.CORRIDOR:
            width = self._estimate_corridor_width(room)
            if width is not None and width < cfg.narrow_corridor_width_mm:
                return StructuralZoneType.CORRIDOR_BAND
            return StructuralZoneType.CORRIDOR_BAND

        if room.type == RoomType.LOBBY:
            return StructuralZoneType.LARGE_OPENING

        if room.type in _OPEN_ROOM_TYPES and room.area_m2 >= cfg.open_plate_min_area_m2:
            return StructuralZoneType.OPEN_FLOOR_PLATE

        return None

    @staticmethod
    def _estimate_corridor_width(room: Room) -> float | None:
        """Return the corridor's short dimension (mm) from its polygon bbox."""
        try:
            poly = Polygon(room.polygon)
            if not poly.is_valid:
                return None
            minx, miny, maxx, maxy = poly.bounds
            return min(maxx - minx, maxy - miny)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Transfer-risk zones
    # ------------------------------------------------------------------

    def _transfer_risk_zones(
        self,
        graph: BuildingGraph,
        story: Story,
        story_areas: dict[str, float],
    ) -> list[StructuralZone]:
        cfg = self.config.zoning
        if len(graph.stories) < 2:
            return []
        min_level = min(s.level for s in graph.stories)
        if story.level != min_level:
            return []

        upper_levels = [s for s in graph.stories if s.level > min_level]
        if not upper_levels:
            return []
        avg_upper = sum(s.floor_area_gross_m2 for s in upper_levels) / len(upper_levels)
        delta = story.floor_area_gross_m2 - avg_upper
        if delta < cfg.transfer_risk_ground_floor_delta_m2:
            return []

        return [
            StructuralZone(
                id=f"zone-transfer-{story.id}",
                type=StructuralZoneType.TRANSFER_RISK,
                polygon=graph.facade.perimeter_polygon,
                story=story.id,
                area_m2=story.floor_area_gross_m2,
                notes=f"Ground floor {delta:.1f}m² larger than upper average",
            )
        ]
