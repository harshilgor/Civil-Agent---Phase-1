"""Completeness score tests — the Step-2 structured
:class:`CompletenessScore` attached to ``BuildingMetadata.completeness``."""

from __future__ import annotations

from src.core.graph_builder import GraphBuilder
from src.schema.building_graph import CompletenessScore, Location
from src.schema.enums import DetectorSource, MaterialPreference, OccupancyType, RoofType
from src.schema.input_models import StructuredInputRequest
from src.utils.completeness_scorer import (
    HUMAN_REVIEW_THRESHOLD,
    annotate_with_completeness,
    build_completeness_score,
)


def _base_request() -> StructuredInputRequest:
    return StructuredInputRequest(
        project_name="Completeness Tower",
        location=Location(lat=0, lng=0),
        length_mm=30000,
        width_mm=20000,
        num_stories=3,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        roof_type=RoofType.FLAT,
    )


class TestBuildCompletenessScore:
    def test_returns_pydantic_model(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        assert isinstance(score, CompletenessScore)

    def test_all_axes_in_unit_range(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        for axis in (score.overall, score.geometry, score.semantics, score.detector_coverage):
            assert 0.0 <= axis <= 1.0

    def test_channel_a_has_high_geometry_and_semantics(self) -> None:
        """Channel A produces full geometry + semantics, so those axes are >= 0.85."""

        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        assert score.geometry >= 0.85
        assert score.semantics >= 0.85

    def test_channel_a_detector_coverage_not_penalised(self) -> None:
        """Channel A has no ML detectors; detector_coverage must stay 1.0.

        Structured-form input is user-authoritative — the user typed every
        element in themselves.  SYMBOL_DETECTOR and YOLO_SEG were never
        supposed to run, so flagging their absence as a deficit would
        incorrectly route clean submissions to the review queue.
        """

        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        assert score.detector_coverage == 1.0

    def test_missing_subsystems_empty_for_channel_a(self) -> None:
        """Channel A should produce an empty missing_subsystems list."""

        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        assert score.missing_subsystems == []
        assert DetectorSource.SYMBOL_DETECTOR.value not in score.missing_subsystems

    def test_channel_a_overall_at_or_near_ceiling(self) -> None:
        """With detector_coverage at 1.0, overall should sit at the ceiling."""

        graph = GraphBuilder().from_structured_input(_base_request())
        score = build_completeness_score(graph)
        assert score.overall >= 0.95


class TestAnnotateWithCompleteness:
    def test_metadata_completeness_populated(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        assert graph.metadata.completeness is not None
        assert isinstance(graph.metadata.completeness, CompletenessScore)

    def test_confidence_scores_overall_matches_completeness_overall(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        assert graph.metadata.completeness is not None
        assert abs(
            graph.metadata.confidence_scores.overall
            - graph.metadata.completeness.overall
        ) < 1e-9

    def test_does_not_flag_human_review_for_full_channel_a(self) -> None:
        """A well-formed Channel A graph shouldn't trip the human-review warning."""

        graph = GraphBuilder().from_structured_input(_base_request())
        assert graph.metadata.completeness.overall >= HUMAN_REVIEW_THRESHOLD
        assert not any(
            w.startswith("requires_human_review") for w in graph.metadata.warnings
        )

    def test_annotate_idempotent(self) -> None:
        """Running annotate twice does not grow the warnings list each time."""

        graph = GraphBuilder().from_structured_input(_base_request())
        first_warnings = list(graph.metadata.warnings)
        annotate_with_completeness(graph)
        assert graph.metadata.warnings == first_warnings
