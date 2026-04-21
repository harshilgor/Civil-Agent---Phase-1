"""Phase 2 test fixtures — extends the base building graph with cores,
shear walls, corridors, and extra openings so structural submodules have
interesting inputs to classify.
"""

from __future__ import annotations

import pytest

from src.schema.building_graph import (
    BuildingGraph,
    BuildingMetadata,
    ConfidenceScores,
    Core,
    Facade,
    Opening,
    Room,
    WallSegment,
)
from src.schema.enums import (
    CoreType,
    InputSource,
    OpeningType,
    RoomType,
    WallType,
)


@pytest.fixture()
def office_tower_graph(sample_building_graph) -> BuildingGraph:
    bg = sample_building_graph
    # Add a centered core
    core = Core(
        id="core-1",
        type=CoreType.ELEVATOR_STAIR,
        polygon=[[14000, 10000], [18000, 10000], [18000, 14000], [14000, 14000]],
        contains_elevator=True,
        contains_stairs=True,
        stories=["story-0", "story-1", "story-2"],
    )
    # Add structural walls around the core + a shear wall
    extra_walls = [
        WallSegment(
            id="wall-core-N",
            type=WallType.STRUCTURAL,
            start=[14000, 14000],
            end=[18000, 14000],
            thickness_mm=300,
            stories=["story-0", "story-1", "story-2"],
        ),
        WallSegment(
            id="wall-core-S",
            type=WallType.STRUCTURAL,
            start=[14000, 10000],
            end=[18000, 10000],
            thickness_mm=300,
            stories=["story-0", "story-1", "story-2"],
        ),
        WallSegment(
            id="wall-shear-1",
            type=WallType.SHEAR_WALL,
            start=[8000, 8000],
            end=[8000, 16000],
            thickness_mm=400,
            stories=["story-0", "story-1", "story-2"],
        ),
    ]
    corridor = Room(
        id="room-corridor-1",
        label="Main Corridor",
        type=RoomType.CORRIDOR,
        polygon=[[6000, 11000], [26000, 11000], [26000, 13000], [6000, 13000], [6000, 11000]],
        area_m2=40.0,
        story="story-1",
    )
    office = Room(
        id="room-office-big",
        label="Open Office",
        type=RoomType.OFFICE,
        polygon=[[0, 0], [32000, 0], [32000, 10000], [0, 10000], [0, 0]],
        area_m2=320.0,
        story="story-1",
    )
    opening = Opening(
        id="opn-garage",
        type=OpeningType.GARAGE_DOOR,
        wall_id="wall-S",
        position_mm=10000,
        width_mm=4000,
        height_mm=3000,
    )
    return BuildingGraph(
        project=bg.project,
        stories=bg.stories,
        grid=bg.grid,
        walls=list(bg.walls) + extra_walls,
        rooms=list(bg.rooms) + [corridor, office],
        openings=[opening],
        column_candidates=bg.column_candidates,
        cores=[core],
        facade=bg.facade,
        metadata=BuildingMetadata(
            input_source=InputSource.STRUCTURED_FORM,
            confidence_scores=ConfidenceScores(overall=1.0),
        ),
    )
