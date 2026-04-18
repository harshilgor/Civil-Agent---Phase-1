"""Export Building Graph to various formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from src.schema.building_graph import BuildingGraph

logger = structlog.get_logger(__name__)


def export_json(bg: BuildingGraph, filepath: str | Path) -> Path:
    """Export Building Graph to a JSON file."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    data = bg.model_dump(mode="json")
    filepath.write_text(json.dumps(data, indent=2))
    logger.info("exported_json", path=str(filepath))
    return filepath


def export_summary_csv(bg: BuildingGraph, filepath: str | Path) -> Path:
    """Export a summary CSV of stories, rooms, and walls."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = ["entity,id,type,area_or_length,story"]

    for story in bg.stories:
        lines.append(f"story,{story.id},{story.usage},{story.floor_area_gross_m2},")

    for room in bg.rooms:
        lines.append(f"room,{room.id},{room.type.value},{room.area_m2},{room.story}")

    for wall in bg.walls:
        import math
        length = math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1])
        stories_str = ";".join(wall.stories)
        lines.append(f"wall,{wall.id},{wall.type.value},{round(length, 2)},{stories_str}")

    filepath.write_text("\n".join(lines))
    logger.info("exported_csv", path=str(filepath))
    return filepath
