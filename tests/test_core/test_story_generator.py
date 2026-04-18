"""Tests for StoryGenerator."""

from __future__ import annotations

import pytest

from src.core.story_generator import StoryGenerator
from src.schema.enums import OccupancyType


@pytest.fixture()
def gen() -> StoryGenerator:
    return StoryGenerator()


class TestBasicStories:
    def test_single_story(self, gen: StoryGenerator):
        stories = gen.generate(num_stories=1, floor_to_floor_mm=3900)
        assert len(stories) == 1
        assert stories[0].level == 0
        assert stories[0].elevation_mm == 0

    def test_three_stories(self, gen: StoryGenerator):
        stories = gen.generate(num_stories=3, floor_to_floor_mm=3600)
        assert len(stories) == 3
        assert stories[0].elevation_mm == 0
        assert stories[1].elevation_mm == 3600
        assert stories[2].elevation_mm == 7200

    def test_story_ids_sequential(self, gen: StoryGenerator):
        stories = gen.generate(num_stories=5)
        ids = [s.id for s in stories]
        assert ids == [f"story-{i}" for i in range(5)]


class TestGroundFloorOverride:
    def test_ground_floor_taller(self, gen: StoryGenerator):
        stories = gen.generate(
            num_stories=3,
            floor_to_floor_mm=3600,
            ground_floor_height_mm=4500,
        )
        assert stories[0].floor_to_floor_mm == 4500
        assert stories[1].floor_to_floor_mm == 3600
        assert stories[1].elevation_mm == 4500
        assert stories[2].elevation_mm == 8100


class TestUsageAssignment:
    def test_default_office_ground_is_lobby(self, gen: StoryGenerator):
        stories = gen.generate(
            num_stories=3,
            occupancy_type=OccupancyType.OFFICE,
        )
        assert stories[0].usage == "LOBBY"
        assert stories[1].usage == "OFFICE"

    def test_custom_usage_by_floor(self, gen: StoryGenerator):
        stories = gen.generate(
            num_stories=3,
            occupancy_type=OccupancyType.MIXED_USE,
            occupancy_by_floor={0: "RETAIL", 1: "OFFICE", 2: "RESIDENTIAL"},
        )
        assert stories[0].usage == "RETAIL"
        assert stories[1].usage == "OFFICE"
        assert stories[2].usage == "RESIDENTIAL"

    def test_residential_ground_is_lobby(self, gen: StoryGenerator):
        stories = gen.generate(num_stories=2, occupancy_type=OccupancyType.RESIDENTIAL)
        assert stories[0].usage == "LOBBY"


class TestFloorArea:
    def test_floor_area_propagated(self, gen: StoryGenerator):
        stories = gen.generate(num_stories=2, floor_area_m2=500)
        for s in stories:
            assert s.floor_area_gross_m2 == 500


class TestValidation:
    def test_zero_stories_raises(self, gen: StoryGenerator):
        with pytest.raises(ValueError, match="num_stories"):
            gen.generate(num_stories=0)
