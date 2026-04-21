"""Tests for :func:`src.core.geometry.cores.detect_cores`."""

from __future__ import annotations

import pytest

from src.core.geometry.config import CoreConfig
from src.core.geometry.cores import detect_cores
from src.schema.building_graph import Room
from src.schema.enums import CoreType, RoomType


def _room(
    id_: str,
    polygon: list[list[float]],
    type_: RoomType,
    story: str = "S1",
) -> Room:
    poly = [[float(x), float(y)] for x, y in polygon]
    xs = [pt[0] for pt in poly]
    ys = [pt[1] for pt in poly]
    area_mm2 = (max(xs) - min(xs)) * (max(ys) - min(ys))
    return Room(
        id=id_,
        label=id_,
        type=type_,
        polygon=poly,
        area_m2=area_mm2 / 1_000_000.0,
        story=story,
        confidence=1.0,
    )


class TestEmpty:
    def test_no_seed_rooms_returns_empty(self):
        rooms = [
            _room("office", [[0, 0], [5000, 0], [5000, 5000], [0, 5000]], RoomType.OFFICE),
        ]
        assert detect_cores(rooms, CoreConfig()) == []


class TestSingleCore:
    def test_lone_stair_becomes_stair_only_core(self):
        rooms = [
            _room(
                "stair",
                [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                RoomType.STAIRWELL,
            )
        ]
        cores = detect_cores(rooms, CoreConfig())
        assert len(cores) == 1
        assert cores[0].type == CoreType.STAIR_ONLY
        assert cores[0].contains_stairs is True
        assert cores[0].contains_elevator is False


class TestClustering:
    def test_adjacent_stair_and_elevator_merge_into_one_core(self):
        rooms = [
            _room(
                "stair",
                [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                RoomType.STAIRWELL,
            ),
            # Elevator is 50mm away from the stair — well inside the
            # default 100mm adjacency_tolerance.
            _room(
                "elev",
                [[3050, 0], [6000, 0], [6000, 3000], [3050, 3000]],
                RoomType.ELEVATOR,
            ),
        ]
        cores = detect_cores(rooms, CoreConfig())
        assert len(cores) == 1
        assert cores[0].type == CoreType.ELEVATOR_STAIR
        assert cores[0].contains_stairs is True
        assert cores[0].contains_elevator is True

    def test_far_apart_seeds_produce_separate_cores(self):
        # Two stairs on opposite ends of a tower.
        rooms = [
            _room(
                "stair_a",
                [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                RoomType.STAIRWELL,
            ),
            _room(
                "stair_b",
                [[50000, 0], [53000, 0], [53000, 3000], [50000, 3000]],
                RoomType.STAIRWELL,
            ),
        ]
        cores = detect_cores(rooms, CoreConfig())
        assert len(cores) == 2

    def test_cluster_below_minimum_area_is_dropped(self):
        # Seed room of 0.25 m² — below default 2.0 m² minimum.
        rooms = [
            _room(
                "tiny_mep",
                [[0, 0], [500, 0], [500, 500], [0, 500]],
                RoomType.MECHANICAL,
            )
        ]
        assert detect_cores(rooms, CoreConfig()) == []


class TestStoryAggregation:
    def test_stories_aggregated_across_cluster(self):
        rooms = [
            _room(
                "stair_l1",
                [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                RoomType.STAIRWELL,
                story="S1",
            ),
            _room(
                "stair_l2",
                [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                RoomType.STAIRWELL,
                story="S2",
            ),
        ]
        cores = detect_cores(rooms, CoreConfig())
        assert len(cores) == 1
        assert set(cores[0].stories) == {"S1", "S2"}
