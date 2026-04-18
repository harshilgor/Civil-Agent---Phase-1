"""Extract room polygons from raw DXF parser output.

Associates nearby text labels with room polygons and classifies room types.
"""

from __future__ import annotations

import structlog
from shapely.geometry import Point, Polygon

from src.schema.enums import RoomType
from src.utils.geometry import polygon_area_m2, polygon_perimeter_mm

logger = structlog.get_logger(__name__)

_LABEL_KEYWORDS: dict[str, RoomType] = {
    "office": RoomType.OFFICE,
    "corridor": RoomType.CORRIDOR,
    "hall": RoomType.CORRIDOR,
    "lobby": RoomType.LOBBY,
    "bath": RoomType.BATHROOM,
    "toilet": RoomType.BATHROOM,
    "wc": RoomType.BATHROOM,
    "kitchen": RoomType.KITCHEN,
    "bedroom": RoomType.BEDROOM,
    "bed": RoomType.BEDROOM,
    "living": RoomType.LIVING_ROOM,
    "storage": RoomType.STORAGE,
    "store": RoomType.STORAGE,
    "mechanical": RoomType.MECHANICAL,
    "mech": RoomType.MECHANICAL,
    "stair": RoomType.STAIRWELL,
    "elevator": RoomType.ELEVATOR,
    "lift": RoomType.ELEVATOR,
    "conference": RoomType.CONFERENCE,
    "meeting": RoomType.CONFERENCE,
    "outdoor": RoomType.OUTDOOR,
    "balcony": RoomType.OUTDOOR,
    "terrace": RoomType.OUTDOOR,
}


class RoomExtractor:
    """Post-process raw room polygons: label, classify, and compute area."""

    def extract(
        self,
        raw_rooms: list[dict],
        text_annotations: list[dict],
        story_id: str = "story-0",
    ) -> list[dict]:
        """Return enriched room dicts ready for Building Graph assembly.

        Each dict has keys: ``polygon``, ``label``, ``type``, ``area_m2``,
        ``perimeter_mm``, ``story``.
        """
        rooms: list[dict] = []
        for i, raw in enumerate(raw_rooms):
            polygon = raw.get("polygon") or []
            if len(polygon) < 3:
                continue

            label = raw.get("label") or self._find_label(polygon, text_annotations)
            room_type = self._classify(label) if label else RoomType.UNDEFINED
            area = polygon_area_m2(polygon)
            perimeter = polygon_perimeter_mm(polygon)

            rooms.append({
                "id": f"room-{story_id}-{i}",
                "polygon": polygon,
                "label": label or f"Room {i + 1}",
                "type": room_type.value,
                "area_m2": round(area, 2),
                "perimeter_mm": round(perimeter, 2),
                "story": story_id,
            })

        logger.info("rooms_extracted", count=len(rooms))
        return rooms

    @staticmethod
    def _find_label(polygon: list[list[float]], texts: list[dict]) -> str | None:
        """Find text annotation that falls inside the polygon."""
        try:
            shape = Polygon(polygon)
        except Exception:
            return None

        for t in texts:
            pt = Point(t["position"])
            if shape.contains(pt):
                return t["text"].strip()
        return None

    @staticmethod
    def _classify(label: str) -> RoomType:
        low = label.lower()
        for keyword, rtype in _LABEL_KEYWORDS.items():
            if keyword in low:
                return rtype
        return RoomType.UNDEFINED
