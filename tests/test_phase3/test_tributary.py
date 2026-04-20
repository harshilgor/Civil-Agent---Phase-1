"""Tests for the tributary area engine."""

from __future__ import annotations

from collections import defaultdict

import pytest

from src.phase3.engines.tributary import compute_tributary_areas


def test_voronoi_tributary_areas_sum_to_floor_area(
    sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
):
    results, _warnings = compute_tributary_areas(
        sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
    )
    assert results, "must produce tributary results"

    # Total floor area from the office_rc fixture: 4*9 m x 3*8 m = 864 m^2
    expected_floor_area_m2 = (4 * 9.0) * (3 * 8.0)

    story_sums: dict[str, float] = defaultdict(float)
    for r in results:
        story_sums[r.story_id] += r.tributary_area_m2

    for story_id, total in story_sums.items():
        rel_err = abs(total - expected_floor_area_m2) / expected_floor_area_m2
        assert rel_err < 0.01, (
            f"story {story_id}: sum={total:.2f} vs floor={expected_floor_area_m2:.2f} "
            f"(rel_err={rel_err:.4f})"
        )


def test_corner_column_classification(
    sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
):
    results, _ = compute_tributary_areas(
        sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
    )
    corners = [r for r in results if r.is_corner_column]
    assert corners, "at least one corner column must be classified"


def test_edge_column_classification(
    sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
):
    results, _ = compute_tributary_areas(
        sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
    )
    edges = [r for r in results if r.is_edge_column and not r.is_corner_column]
    assert edges, "at least one pure edge (non-corner) column must be classified"


def test_interior_column_classification(
    sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
):
    results, _ = compute_tributary_areas(
        sample_building_graph_office_rc, sample_structural_design_graph, empty_builder
    )
    interiors = [r for r in results if r.is_interior_column]
    assert interiors, "at least one interior column must be classified"


def test_fallback_with_two_supports(
    sample_building_graph_office_rc, empty_builder
):
    """With < 3 supports the engine must fall back to equal-area division."""

    stories = sample_building_graph_office_rc["stories"]
    story_id = stories[0]["id"]
    sg = {
        "building_graph_id": "test",
        "support_candidates": [
            {
                "id": "A",
                "position": [9000.0, 8000.0],
                "story": story_id,
                "classification": "preferred",
                "score": 0.9,
                "reasons": [],
                "penalties": [],
            },
            {
                "id": "B",
                "position": [18000.0, 16000.0],
                "story": story_id,
                "classification": "preferred",
                "score": 0.9,
                "reasons": [],
                "penalties": [],
            },
        ],
        "metadata": {},
    }
    results, warnings = compute_tributary_areas(
        sample_building_graph_office_rc, sg, empty_builder
    )
    assert any(r.computation_method == "equal_division_fallback" for r in results)
    assert any(w.code == "P3W007" or w.code == "P3W012" for w in warnings)
