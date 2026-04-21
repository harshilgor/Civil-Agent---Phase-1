"""Tests for :func:`src.core.geometry.rooms.extract_rooms`."""

from __future__ import annotations

import pytest

from src.core.geometry.config import RoomConfig
from src.core.geometry.rooms import RoomHint, extract_rooms
from src.schema.enums import RoomType

from .conftest import wall


class TestSingleRoom:
    def test_square_room_extracts_one_polygon(self, square_room_walls):
        rooms = extract_rooms(square_room_walls, RoomConfig())
        assert len(rooms) == 1
        room = rooms[0]
        assert room.area_m2 == pytest.approx(25.0, abs=0.01)  # 5m × 5m
        assert len(room.polygon) == 4

    def test_tiny_room_dropped_when_below_minimum(self):
        # 500mm × 500mm room = 0.25 m² < 1.0 m² minimum.
        tiny = [
            wall("n", (0.0, 500.0), (500.0, 500.0)),
            wall("e", (500.0, 500.0), (500.0, 0.0)),
            wall("s", (500.0, 0.0), (0.0, 0.0)),
            wall("w", (0.0, 0.0), (0.0, 500.0)),
        ]
        assert extract_rooms(tiny, RoomConfig(minimum_area_m2=1.0)) == []


class TestTwoRooms:
    def test_divided_rectangle_yields_two_rooms(self):
        # 10m × 5m rectangle divided in the middle by a vertical wall.
        walls = [
            wall("n", (0.0, 5000.0), (10000.0, 5000.0)),
            wall("e", (10000.0, 5000.0), (10000.0, 0.0)),
            wall("s", (10000.0, 0.0), (0.0, 0.0)),
            wall("w", (0.0, 0.0), (0.0, 5000.0)),
            wall("mid", (5000.0, 0.0), (5000.0, 5000.0)),
        ]
        rooms = extract_rooms(walls, RoomConfig())
        assert len(rooms) == 2
        # Both rooms are 5m × 5m = 25 m².
        for room in rooms:
            assert room.area_m2 == pytest.approx(25.0, abs=0.01)

    def test_rooms_sorted_by_descending_area(self):
        # Asymmetric split: 3m vs. 7m wide.
        walls = [
            wall("n", (0.0, 5000.0), (10000.0, 5000.0)),
            wall("e", (10000.0, 5000.0), (10000.0, 0.0)),
            wall("s", (10000.0, 0.0), (0.0, 0.0)),
            wall("w", (0.0, 0.0), (0.0, 5000.0)),
            wall("mid", (3000.0, 0.0), (3000.0, 5000.0)),
        ]
        rooms = extract_rooms(walls, RoomConfig())
        assert len(rooms) == 2
        assert rooms[0].area_m2 > rooms[1].area_m2
        assert rooms[0].area_m2 == pytest.approx(35.0, abs=0.01)  # 7 × 5
        assert rooms[1].area_m2 == pytest.approx(15.0, abs=0.01)  # 3 × 5


class TestHints:
    def test_hint_applies_room_type_by_centroid(self, square_room_walls):
        hints = [
            RoomHint(
                polygon=[
                    [100.0, 100.0],
                    [4900.0, 100.0],
                    [4900.0, 4900.0],
                    [100.0, 4900.0],
                ],
                room_type=RoomType.BEDROOM,
                label="Master Bedroom",
            )
        ]
        rooms = extract_rooms(square_room_walls, RoomConfig(), hints=hints)
        assert rooms[0].type == RoomType.BEDROOM
        assert rooms[0].label == "Master Bedroom"

    def test_no_matching_hint_keeps_undefined(self, square_room_walls):
        # Hint polygon is well outside the square — not matched.
        hints = [
            RoomHint(
                polygon=[
                    [20000.0, 20000.0],
                    [30000.0, 20000.0],
                    [30000.0, 30000.0],
                    [20000.0, 30000.0],
                ],
                room_type=RoomType.BEDROOM,
                label="Elsewhere",
            )
        ]
        rooms = extract_rooms(square_room_walls, RoomConfig(), hints=hints)
        assert rooms[0].type == RoomType.UNDEFINED


class TestEdgeCases:
    def test_empty_input_returns_empty(self):
        assert extract_rooms([], RoomConfig()) == []

    def test_open_polyline_yields_no_rooms(self):
        # Three walls that don't close — no enclosed face.
        walls = [
            wall("a", (0.0, 0.0), (5000.0, 0.0)),
            wall("b", (5000.0, 0.0), (5000.0, 3000.0)),
            wall("c", (5000.0, 3000.0), (2000.0, 3000.0)),
        ]
        assert extract_rooms(walls, RoomConfig()) == []
