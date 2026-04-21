"""Channel A — structured assumption register tests.

Covers the contract that every default / derivation the Channel-A graph
builder makes lands as a well-formed :class:`AssumptionRecord` on
``BuildingMetadata.assumption_register``.
"""

from __future__ import annotations

import pytest

from src.core.assumption_builder import (
    _DEFAULT_F2F_MM,
    _DEFAULT_PREFERRED_BAY_MM,
    StructuredInputAssumptionBuilder,
    apply_override,
)
from src.core.graph_builder import GraphBuilder
from src.schema.assumptions import AssumptionRecord
from src.schema.enums import ConfidenceLevel, MaterialPreference, OccupancyType, RoofType
from src.schema.input_models import StructuredInputRequest
from src.schema.building_graph import Location


def _base_request(**overrides) -> StructuredInputRequest:
    payload: dict = dict(
        project_name="Assumption Test Tower",
        location=Location(lat=40.7, lng=-74.0, city="NYC", state="NY", country="US"),
        length_mm=32000,
        width_mm=24000,
        num_stories=5,
        floor_to_floor_mm=_DEFAULT_F2F_MM,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        preferred_bay_x_mm=_DEFAULT_PREFERRED_BAY_MM,
        preferred_bay_y_mm=_DEFAULT_PREFERRED_BAY_MM,
        roof_type=RoofType.FLAT,
    )
    payload.update(overrides)
    return StructuredInputRequest(**payload)


# ---------------------------------------------------------------------------
# Builder-unit tests
# ---------------------------------------------------------------------------


class TestStructuredInputAssumptionBuilder:
    def test_records_all_seven_required_fields(self) -> None:
        """Every emitted record must carry the Step-2 specified schema."""

        builder = StructuredInputAssumptionBuilder()
        builder.record_all_request_defaults(_base_request())
        assert builder.records, "Builder produced zero records for a valid request"
        required_attrs = (
            "id",
            "value",
            "unit",
            "source",
            "confidence",
            "rationale",
            "overrideable",
        )
        for record in builder.records:
            assert isinstance(record, AssumptionRecord)
            for attr in required_attrs:
                assert hasattr(record, attr), f"Missing field {attr!r} on {record.id!r}"
            assert record.id.startswith("channel_a_")
            assert 0.0 <= record.confidence <= 1.0
            assert record.rationale  # non-empty
            assert record.source  # non-empty

    def test_confidence_level_matches_numeric_bucket(self) -> None:
        builder = StructuredInputAssumptionBuilder()
        builder.record_all_request_defaults(_base_request())
        for record in builder.records:
            if record.confidence >= 0.85:
                assert record.confidence_level == ConfidenceLevel.HIGH
            elif record.confidence >= 0.60:
                assert record.confidence_level == ConfidenceLevel.MEDIUM
            else:
                assert record.confidence_level == ConfidenceLevel.LOW

    def test_user_supplied_values_score_higher_than_defaults(self) -> None:
        """A non-default floor-to-floor height should carry confidence 1.0."""

        default_builder = StructuredInputAssumptionBuilder()
        default_builder.record_floor_to_floor(_base_request())
        assert default_builder.records[-1].confidence < 1.0  # default applied

        custom_builder = StructuredInputAssumptionBuilder()
        custom_builder.record_floor_to_floor(_base_request(floor_to_floor_mm=4500))
        assert custom_builder.records[-1].confidence == 1.0  # user-supplied

    def test_input_source_immutable_record_flagged_non_overrideable(self) -> None:
        builder = StructuredInputAssumptionBuilder()
        builder.record_input_source_immutable()
        [rec] = builder.records
        assert rec.overrideable is False
        assert rec.value == "STRUCTURED_FORM"
        assert rec.id == "channel_a_input_source"

    def test_unique_ids(self) -> None:
        builder = StructuredInputAssumptionBuilder()
        builder.record_all_request_defaults(_base_request())
        builder.record_perimeter_wall_thickness(200.0)
        builder.record_perimeter_wall_type("FACADE")
        builder.record_single_room_per_floor(5)
        ids = [r.id for r in builder.records]
        assert len(ids) == len(set(ids)), f"Duplicate ids in register: {ids}"


# ---------------------------------------------------------------------------
# Graph-builder integration
# ---------------------------------------------------------------------------


class TestGraphBuilderAssumptionRegister:
    def test_register_is_populated(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        assert len(graph.metadata.assumption_register) >= 8, (
            "Expected at least 8 structured assumptions for a full Channel A "
            "payload (channel marker + form defaults + wall + room heuristics)"
        )

    def test_register_contains_input_source_marker(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        marker = next(
            (r for r in graph.metadata.assumption_register if r.id == "channel_a_input_source"),
            None,
        )
        assert marker is not None
        assert marker.overrideable is False

    def test_register_contains_wall_thickness(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        thick = next(
            (r for r in graph.metadata.assumption_register if r.id == "channel_a_wall_thickness_perimeter"),
            None,
        )
        assert thick is not None
        assert thick.unit == "mm"
        assert thick.value == 200.0

    def test_legacy_string_list_still_populated_for_back_compat(self) -> None:
        """Older consumers read ``assumptions_made``; the upgrade preserves it."""

        graph = GraphBuilder().from_structured_input(_base_request())
        assert graph.metadata.assumptions_made
        assert all(isinstance(s, str) for s in graph.metadata.assumptions_made)


# ---------------------------------------------------------------------------
# Override helper
# ---------------------------------------------------------------------------


class TestApplyOverride:
    def test_happy_path_marks_was_overridden(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        register = graph.metadata.assumption_register
        result = apply_override(
            register,
            assumption_id="channel_a_preferred_bay_x",
            value=9000,
            source="reviewer:test",
        )
        assert result is not None
        assert result.was_overridden is True
        assert result.override_value == 9000
        assert result.override_source == "reviewer:test"
        assert result.effective_value == 9000

    def test_unknown_id_returns_none(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        result = apply_override(
            graph.metadata.assumption_register,
            assumption_id="channel_a_does_not_exist",
            value=1,
            source="x",
        )
        assert result is None

    def test_non_overrideable_raises(self) -> None:
        graph = GraphBuilder().from_structured_input(_base_request())
        with pytest.raises(ValueError, match="overrideable=False"):
            apply_override(
                graph.metadata.assumption_register,
                assumption_id="channel_a_input_source",
                value="CAD_DIRECT",
                source="x",
            )
