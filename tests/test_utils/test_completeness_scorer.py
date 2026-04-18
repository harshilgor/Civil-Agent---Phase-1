"""Tests for the completeness scorer (Gap 8)."""

from __future__ import annotations

import pytest

from src.schema.building_graph import (
    BuildingGraph,
    BuildingMetadata,
    ConfidenceScores,
    Facade,
    GridSystem,
)
from src.schema.enums import InputSource
from src.utils.completeness_scorer import (
    HUMAN_REVIEW_THRESHOLD,
    CompletenessScorer,
    annotate_with_completeness,
)


def test_fully_populated_graph_scores_high(sample_building_graph: BuildingGraph) -> None:
    scorer = CompletenessScorer()
    report = scorer.score(sample_building_graph)
    assert report.overall_completeness > 0.7
    assert "project_info" in report.section_scores
    assert report.section_scores["project_info"] >= 0.9
    assert report.section_scores["facade"] == 1.0


def test_empty_sections_warn_and_lower_score(sample_building_graph: BuildingGraph) -> None:
    bg = sample_building_graph.model_copy(update={
        "column_candidates": [],
        "openings": [],
        "cores": [],
    })
    scorer = CompletenessScorer()
    report = scorer.score(bg)
    assert any("column" in w.lower() for w in report.warnings)
    assert any("opening" in w.lower() for w in report.warnings)
    assert report.section_scores["column_candidates"] == 0.0


def test_missing_grid_warns(sample_building_graph: BuildingGraph) -> None:
    empty_grid = GridSystem(x_lines=[], y_lines=[], bays=[])
    bg = sample_building_graph.model_copy(update={"grid": empty_grid})
    report = CompletenessScorer().score(bg)
    assert report.section_scores["grid"] == 0.0
    assert any("grid" in w.lower() for w in report.warnings)


def test_annotate_adds_warnings_to_metadata(sample_building_graph: BuildingGraph) -> None:
    # Force a low completeness: strip out walls, rooms, grid
    empty_grid = GridSystem(x_lines=[], y_lines=[], bays=[])
    bg = sample_building_graph.model_copy(update={
        "walls": [],
        "rooms": [],
        "column_candidates": [],
        "openings": [],
        "grid": empty_grid,
    })
    annotated = annotate_with_completeness(bg)
    assert annotated.metadata.confidence_scores.overall < HUMAN_REVIEW_THRESHOLD
    assert any("requires_human_review" in w for w in annotated.metadata.warnings)


def test_section_weights_sum_to_one() -> None:
    from src.utils.completeness_scorer import _WEIGHTS

    total = sum(_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6


def test_report_to_dict(sample_building_graph: BuildingGraph) -> None:
    report = CompletenessScorer().score(sample_building_graph)
    d = report.to_dict()
    assert "overall_completeness" in d
    assert "section_scores" in d
    assert set(d["section_scores"].keys()) == {
        "project_info", "stories", "grid", "walls", "rooms",
        "openings", "column_candidates", "cores", "facade",
    }
