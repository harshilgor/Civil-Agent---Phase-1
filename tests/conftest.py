"""Shared pytest fixtures for the Civil Agent test suite."""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Conditional-skip hooks for infra-dependent markers.
#
# Tests that need live infrastructure are marked in-module (e.g. with
# ``@pytest.mark.requires_redis``).  CI opts in by exporting the matching
# ``RUN_REQUIRES_*`` env var; local dev runs skip them by default so they
# never silently block a pytest session.
# ---------------------------------------------------------------------------

_INFRA_MARKERS = {
    "requires_redis": (
        "RUN_REQUIRES_REDIS",
        "needs a live Redis broker — set RUN_REQUIRES_REDIS=1 to run",
    ),
    "requires_gpu": (
        "RUN_REQUIRES_GPU",
        "needs a CUDA-capable GPU — set RUN_REQUIRES_GPU=1 to run",
    ),
    "requires_weights": (
        "RUN_REQUIRES_WEIGHTS",
        "needs real model weights on disk — set RUN_REQUIRES_WEIGHTS=1 to run",
    ),
}


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for marker_name, (env_var, reason) in _INFRA_MARKERS.items():
        if os.environ.get(env_var, "").lower() in {"1", "true", "yes"}:
            continue
        skip_marker = pytest.mark.skip(reason=reason)
        for item in items:
            if marker_name in item.keywords:
                item.add_marker(skip_marker)

from src.schema.building_graph import (
    Bay,
    BuildingGraph,
    BuildingMetadata,
    ColumnCandidate,
    ConfidenceScores,
    Core,
    Facade,
    GridLine,
    GridSystem,
    Location,
    Opening,
    ProjectInfo,
    Room,
    Story,
    WallSegment,
)
from src.schema.enums import (
    CoreType,
    InputSource,
    MaterialPreference,
    OccupancyType,
    RoomType,
    WallType,
)
from src.schema.input_models import StructuredInputRequest


@pytest.fixture()
def sample_location() -> Location:
    return Location(
        lat=37.7749,
        lng=-122.4194,
        city="San Francisco",
        state="CA",
        country="US",
        seismic_zone="D",
        wind_speed_mph=110,
    )


@pytest.fixture()
def sample_project_info(sample_location: Location) -> ProjectInfo:
    return ProjectInfo(
        name="Test Office Tower",
        location=sample_location,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        num_stories=3,
        total_height_mm=11700,
    )


@pytest.fixture()
def sample_stories() -> list[Story]:
    return [
        Story(
            id="story-0",
            level=0,
            floor_to_floor_mm=4500,
            elevation_mm=0,
            floor_area_gross_m2=800,
            usage="LOBBY",
        ),
        Story(
            id="story-1",
            level=1,
            floor_to_floor_mm=3600,
            elevation_mm=4500,
            floor_area_gross_m2=800,
            usage="OFFICE",
        ),
        Story(
            id="story-2",
            level=2,
            floor_to_floor_mm=3600,
            elevation_mm=8100,
            floor_area_gross_m2=800,
            usage="OFFICE",
        ),
    ]


@pytest.fixture()
def sample_grid() -> GridSystem:
    x_lines = [
        GridLine(id="A", position_mm=0),
        GridLine(id="B", position_mm=8000),
        GridLine(id="C", position_mm=16000),
        GridLine(id="D", position_mm=24000),
        GridLine(id="E", position_mm=32000),
    ]
    y_lines = [
        GridLine(id="1", position_mm=0),
        GridLine(id="2", position_mm=8000),
        GridLine(id="3", position_mm=16000),
        GridLine(id="4", position_mm=24000),
    ]
    bays = [
        Bay(
            id=f"bay-{x.id}-{y.id}",
            span_x_mm=8000,
            span_y_mm=8000,
            grid_x_start=x.id,
            grid_x_end=x_lines[i + 1].id,
            grid_y_start=y.id,
            grid_y_end=y_lines[j + 1].id,
        )
        for i, x in enumerate(x_lines[:-1])
        for j, y in enumerate(y_lines[:-1])
    ]
    return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays)


@pytest.fixture()
def sample_walls() -> list[WallSegment]:
    return [
        WallSegment(
            id="wall-N",
            type=WallType.FACADE,
            start=[0, 24000],
            end=[32000, 24000],
            thickness_mm=200,
            stories=["story-0", "story-1", "story-2"],
        ),
        WallSegment(
            id="wall-S",
            type=WallType.FACADE,
            start=[0, 0],
            end=[32000, 0],
            thickness_mm=200,
            stories=["story-0", "story-1", "story-2"],
        ),
        WallSegment(
            id="wall-E",
            type=WallType.FACADE,
            start=[32000, 0],
            end=[32000, 24000],
            thickness_mm=200,
            stories=["story-0", "story-1", "story-2"],
        ),
        WallSegment(
            id="wall-W",
            type=WallType.FACADE,
            start=[0, 0],
            end=[0, 24000],
            thickness_mm=200,
            stories=["story-0", "story-1", "story-2"],
        ),
    ]


@pytest.fixture()
def sample_rooms() -> list[Room]:
    return [
        Room(
            id="room-lobby",
            label="Lobby",
            type=RoomType.LOBBY,
            polygon=[[0, 0], [32000, 0], [32000, 24000], [0, 24000], [0, 0]],
            area_m2=768.0,
            story="story-0",
        ),
    ]


@pytest.fixture()
def sample_facade() -> Facade:
    return Facade(
        perimeter_polygon=[
            [0, 0], [32000, 0], [32000, 24000], [0, 24000], [0, 0]
        ],
        perimeter_length_mm=112000,
    )


@pytest.fixture()
def sample_column_candidates() -> list[ColumnCandidate]:
    return [
        ColumnCandidate(position=[0, 0], grid_intersection="A-1", confidence=1.0, is_required=True),
        ColumnCandidate(position=[8000, 0], grid_intersection="B-1", confidence=0.9),
    ]


@pytest.fixture()
def sample_metadata() -> BuildingMetadata:
    return BuildingMetadata(
        input_source=InputSource.STRUCTURED_FORM,
        confidence_scores=ConfidenceScores(overall=1.0),
        assumptions_made=["Assumed regular grid"],
    )


@pytest.fixture()
def sample_building_graph(
    sample_project_info,
    sample_stories,
    sample_grid,
    sample_walls,
    sample_rooms,
    sample_facade,
    sample_column_candidates,
    sample_metadata,
) -> BuildingGraph:
    return BuildingGraph(
        project=sample_project_info,
        stories=sample_stories,
        grid=sample_grid,
        walls=sample_walls,
        rooms=sample_rooms,
        openings=[],
        column_candidates=sample_column_candidates,
        cores=[],
        facade=sample_facade,
        metadata=sample_metadata,
    )


@pytest.fixture()
def sample_structured_request(sample_location: Location) -> StructuredInputRequest:
    return StructuredInputRequest(
        project_name="Test Office",
        location=sample_location,
        length_mm=32000,
        width_mm=24000,
        num_stories=3,
        floor_to_floor_mm=3600,
        ground_floor_height_mm=4500,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        preferred_bay_x_mm=8000,
        preferred_bay_y_mm=8000,
    )
