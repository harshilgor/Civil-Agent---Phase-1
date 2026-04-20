"""Tests for the story load aggregation engine."""

from __future__ import annotations

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.engines.dead_load import compute_dead_loads
from src.phase3.engines.live_load import compute_live_loads
from src.phase3.engines.story_loads import (
    DEFAULT_SEISMIC_LIVE_FRACTION,
    compute_story_loads,
)
from src.phase3.models.enums import MaterialFamily


def test_cumulative_dead_increases_to_foundation(
    sample_building_graph_office_rc,
):
    builder = AssumptionBuilder()
    dead = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, builder
    )
    live = compute_live_loads(sample_building_graph_office_rc, builder)
    results = compute_story_loads(
        sample_building_graph_office_rc, dead, live, builder
    )
    assert len(results) == len(sample_building_graph_office_rc["stories"])
    # Results are ordered roof -> ground, so cumulative should grow monotonically.
    prev = -1.0
    for r in results:
        assert r.cumulative_dead_kN >= prev
        prev = r.cumulative_dead_kN


def test_story_weight_uses_25_percent_live_for_seismic(
    sample_building_graph_office_rc,
):
    builder = AssumptionBuilder()
    dead = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, builder
    )
    live = compute_live_loads(sample_building_graph_office_rc, builder)
    results = compute_story_loads(
        sample_building_graph_office_rc, dead, live, builder
    )
    # Office story (not roof): W_story = D + 0.25 * L
    office_story = next(r for r in results if r.floor_area_m2 > 0 and r.total_live_kN > 0)
    expected = office_story.total_dead_kN + DEFAULT_SEISMIC_LIVE_FRACTION * office_story.total_live_kN
    assert office_story.story_weight_kN == pytest.approx(expected, rel=1e-6)


def test_story_count_matches_building_graph(sample_building_graph_office_rc):
    builder = AssumptionBuilder()
    dead = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, builder
    )
    live = compute_live_loads(sample_building_graph_office_rc, builder)
    results = compute_story_loads(
        sample_building_graph_office_rc, dead, live, builder
    )
    assert len(results) == sample_building_graph_office_rc["project"]["num_stories"]
