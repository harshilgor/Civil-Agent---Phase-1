"""Tests for wall-type-aware column scoring (Gap 6)."""

from __future__ import annotations

import pytest

from src.core.zone_classifier import ZoneClassifier
from src.schema.building_graph import Bay, GridLine, GridSystem, WallSegment
from src.schema.enums import WallType


@pytest.fixture()
def small_grid() -> GridSystem:
    x_lines = [
        GridLine(id="A", position_mm=0),
        GridLine(id="B", position_mm=8000),
        GridLine(id="C", position_mm=16000),
    ]
    y_lines = [
        GridLine(id="1", position_mm=0),
        GridLine(id="2", position_mm=8000),
        GridLine(id="3", position_mm=16000),
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


def _walls_at_structural_intersection() -> list[WallSegment]:
    """Two STRUCTURAL walls crossing at (8000, 8000) — the center of the 3x3 grid."""
    return [
        WallSegment(
            id="w-x",
            type=WallType.STRUCTURAL,
            start=[0, 8000],
            end=[16000, 8000],
            thickness_mm=200,
            stories=["story-0"],
        ),
        WallSegment(
            id="w-y",
            type=WallType.STRUCTURAL,
            start=[8000, 0],
            end=[8000, 16000],
            thickness_mm=200,
            stories=["story-0"],
        ),
    ]


def _walls_at_partition_intersection() -> list[WallSegment]:
    return [
        WallSegment(
            id="p-x",
            type=WallType.PARTITION,
            start=[0, 8000],
            end=[16000, 8000],
            thickness_mm=100,
            stories=["story-0"],
        ),
        WallSegment(
            id="p-y",
            type=WallType.PARTITION,
            start=[8000, 0],
            end=[8000, 16000],
            thickness_mm=100,
            stories=["story-0"],
        ),
    ]


# ---------------------------------------------------------------------------


def test_structural_intersections_score_higher_than_partition(small_grid: GridSystem) -> None:
    classifier = ZoneClassifier()

    structural = classifier.identify_columns(
        small_grid, walls=_walls_at_structural_intersection()
    )
    partition = classifier.identify_columns(
        small_grid, walls=_walls_at_partition_intersection()
    )

    # Interior candidate at (8000, 8000)
    structural_interior = next(c for c in structural if c.grid_intersection == "B-2")
    partition_interior = next(c for c in partition if c.grid_intersection == "B-2")

    assert structural_interior.confidence > partition_interior.confidence
    # Partition intersection should be heavily penalised
    assert partition_interior.confidence < 0.3


def test_shear_wall_intersection_gets_bonus(small_grid: GridSystem) -> None:
    shear_walls = [
        WallSegment(
            id="s-x",
            type=WallType.SHEAR_WALL,
            start=[0, 8000],
            end=[16000, 8000],
            thickness_mm=300,
            stories=["story-0"],
        ),
        WallSegment(
            id="s-y",
            type=WallType.SHEAR_WALL,
            start=[8000, 0],
            end=[8000, 16000],
            thickness_mm=300,
            stories=["story-0"],
        ),
    ]
    classifier = ZoneClassifier()
    result = classifier.identify_columns(small_grid, walls=shear_walls)
    interior = next(c for c in result if c.grid_intersection == "B-2")
    # Base interior is 0.85, shear mult is 1.2, clamped to 1.0
    assert interior.confidence >= 0.95


def test_facade_corner_gets_slight_bonus(small_grid: GridSystem) -> None:
    facade = [
        WallSegment(
            id="f-N",
            type=WallType.FACADE,
            start=[0, 16000],
            end=[16000, 16000],
            thickness_mm=200,
            stories=["story-0"],
        ),
        WallSegment(
            id="f-S",
            type=WallType.FACADE,
            start=[0, 0],
            end=[16000, 0],
            thickness_mm=200,
            stories=["story-0"],
        ),
        WallSegment(
            id="f-E",
            type=WallType.FACADE,
            start=[16000, 0],
            end=[16000, 16000],
            thickness_mm=200,
            stories=["story-0"],
        ),
        WallSegment(
            id="f-W",
            type=WallType.FACADE,
            start=[0, 0],
            end=[0, 16000],
            thickness_mm=200,
            stories=["story-0"],
        ),
    ]
    classifier = ZoneClassifier()
    result = classifier.identify_columns(small_grid, walls=facade)
    corner = next(c for c in result if c.grid_intersection == "A-1")
    # Corner base 1.0 * 1.1 → clamped to 1.0
    assert corner.confidence == 1.0
    assert corner.is_required is True


def test_low_wall_confidence_blends_toward_one(small_grid: GridSystem) -> None:
    classifier = ZoneClassifier()
    low_conf = classifier.identify_columns(
        small_grid, walls=_walls_at_partition_intersection(), wall_type_confidence=0.3
    )
    # With low confidence, the harsh partition penalty should blend toward 1.0
    interior_low = next(c for c in low_conf if c.grid_intersection == "B-2")

    high_conf = classifier.identify_columns(
        small_grid, walls=_walls_at_partition_intersection(), wall_type_confidence=0.95
    )
    interior_high = next(c for c in high_conf if c.grid_intersection == "B-2")

    assert interior_low.confidence > interior_high.confidence


def test_no_walls_returns_base_scores(small_grid: GridSystem) -> None:
    classifier = ZoneClassifier()
    result = classifier.identify_columns(small_grid)
    # Corner candidate
    corner = next(c for c in result if c.grid_intersection == "A-1")
    interior = next(c for c in result if c.grid_intersection == "B-2")
    assert corner.confidence == 1.0
    assert interior.confidence == 0.85
