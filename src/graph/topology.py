"""Topological analysis of the building graph.

Provides room connectivity, escape route analysis, and structural
system identification.
"""

from __future__ import annotations

import structlog

from src.schema.building_graph import BuildingGraph, Room
from src.schema.enums import RoomType

logger = structlog.get_logger(__name__)


def find_escape_rooms(bg: BuildingGraph) -> list[str]:
    """Identify rooms that serve as escape routes (stairs, corridors)."""
    return [
        r.id for r in bg.rooms
        if r.type in (RoomType.STAIRWELL, RoomType.CORRIDOR, RoomType.LOBBY)
    ]


def find_service_rooms(bg: BuildingGraph) -> list[str]:
    """Identify service rooms (mechanical, storage, bathrooms)."""
    return [
        r.id for r in bg.rooms
        if r.type in (RoomType.MECHANICAL, RoomType.STORAGE, RoomType.BATHROOM)
    ]


def compute_floor_efficiency(bg: BuildingGraph) -> dict[str, float]:
    """Compute net-to-gross floor area ratio per storey."""
    result: dict[str, float] = {}
    for story in bg.stories:
        story_rooms = [r for r in bg.rooms if r.story == story.id]
        usable_area = sum(
            r.area_m2 for r in story_rooms
            if r.type not in (RoomType.CORRIDOR, RoomType.STAIRWELL, RoomType.ELEVATOR, RoomType.MECHANICAL)
        )
        gross = story.floor_area_gross_m2
        result[story.id] = round(usable_area / gross, 3) if gross > 0 else 0
    return result
