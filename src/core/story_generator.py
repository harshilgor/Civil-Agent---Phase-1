"""Story stack generation.

Generates a list of ``Story`` objects given the number of floors,
floor-to-floor heights, and per-floor usage overrides.
"""

from __future__ import annotations

import structlog

from src.schema.building_graph import Story
from src.schema.enums import OccupancyType

logger = structlog.get_logger(__name__)

# Default floor-to-floor heights (mm) by occupancy when not specified
_DEFAULT_HEIGHTS: dict[OccupancyType, float] = {
    OccupancyType.OFFICE: 3900,
    OccupancyType.RESIDENTIAL: 3200,
    OccupancyType.MIXED_USE: 3600,
    OccupancyType.RETAIL: 4500,
    OccupancyType.INDUSTRIAL: 6000,
    OccupancyType.EDUCATIONAL: 3900,
    OccupancyType.HEALTHCARE: 4200,
    OccupancyType.HOSPITALITY: 3400,
    OccupancyType.PARKING: 3000,
}


class StoryGenerator:
    """Generate a building story stack."""

    def generate(
        self,
        num_stories: int,
        floor_to_floor_mm: float = 3900,
        ground_floor_height_mm: float | None = None,
        roof_type: str = "FLAT",
        occupancy_type: OccupancyType = OccupancyType.OFFICE,
        occupancy_by_floor: dict[int, str] | None = None,
        floor_area_m2: float = 0,
    ) -> list[Story]:
        """Create stories with cumulative elevations and per-floor usage.

        Args:
            num_stories: Total number of above-grade stories (>= 1).
            floor_to_floor_mm: Typical storey height in mm.
            ground_floor_height_mm: Override for level 0 (e.g. taller lobby).
            roof_type: ``"FLAT"`` or ``"PITCHED"`` — metadata only.
            occupancy_type: Default occupancy applied to each floor.
            occupancy_by_floor: ``{level: usage_label}`` overrides.
            floor_area_m2: Gross floor area per storey.

        Returns:
            Ordered list of ``Story`` from level 0 upward.
        """
        if num_stories < 1:
            raise ValueError("num_stories must be >= 1")

        occupancy_by_floor = occupancy_by_floor or {}
        default_usage = occupancy_type.value

        stories: list[Story] = []
        elevation = 0.0

        for level in range(num_stories):
            if level == 0 and ground_floor_height_mm is not None:
                height = ground_floor_height_mm
            else:
                height = floor_to_floor_mm

            usage = occupancy_by_floor.get(level, default_usage)
            if level == 0 and level not in occupancy_by_floor:
                usage = self._infer_ground_usage(occupancy_type)

            stories.append(
                Story(
                    id=f"story-{level}",
                    level=level,
                    floor_to_floor_mm=height,
                    elevation_mm=elevation,
                    floor_area_gross_m2=floor_area_m2,
                    usage=usage,
                )
            )
            elevation += height

        logger.info(
            "stories_generated",
            count=num_stories,
            total_height_mm=elevation,
            roof_type=roof_type,
        )
        return stories

    @staticmethod
    def _infer_ground_usage(occupancy: OccupancyType) -> str:
        """Ground-floor usage heuristic: offices typically have a lobby."""
        ground_map: dict[OccupancyType, str] = {
            OccupancyType.OFFICE: "LOBBY",
            OccupancyType.RESIDENTIAL: "LOBBY",
            OccupancyType.MIXED_USE: "RETAIL",
            OccupancyType.RETAIL: "RETAIL",
            OccupancyType.HOSPITALITY: "LOBBY",
        }
        return ground_map.get(occupancy, occupancy.value)
