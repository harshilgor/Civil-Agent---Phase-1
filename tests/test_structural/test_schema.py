"""Schema validation tests for the Structural Design Graph."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema.structural_enums import (
    ConstraintPriority,
    ConstraintType,
    ForbiddenReason,
    FramingDirection,
    GravitySystemType,
    LateralSystemType,
    StructuralZoneType,
    SupportCandidateClass,
    SupportCandidateReason,
)
from src.schema.structural_graph import (
    ForbiddenRegion,
    FramingZone,
    GravitySystemCandidate,
    LateralSystemCandidate,
    SpanInfo,
    SpanMap,
    StructuralConstraint,
    StructuralDesignGraph,
    StructuralMetadata,
    StructuralZone,
    SupportCandidate,
    VerticalAlignmentGroup,
)


def test_empty_graph_is_valid():
    sdg = StructuralDesignGraph(building_graph_id="bg-1")
    assert sdg.zones == []
    assert sdg.constraints == []
    assert sdg.metadata.confidence_overall == 0.0


def test_support_candidate_score_bounds():
    with pytest.raises(ValidationError):
        SupportCandidate(
            id="s1",
            position=[0, 0],
            story="s0",
            classification=SupportCandidateClass.STRONG,
            score=1.5,
        )


def test_support_candidate_position_length():
    with pytest.raises(ValidationError):
        SupportCandidate(
            id="s1",
            position=[0],
            story="s0",
            classification=SupportCandidateClass.STRONG,
            score=0.5,
        )


def test_support_candidate_valid():
    s = SupportCandidate(
        id="s1", position=[0, 0], story="s0",
        classification=SupportCandidateClass.STRONG, score=0.9,
        reasons=[SupportCandidateReason.GRID_INTERSECTION],
    )
    assert s.score == 0.9


def test_zone_requires_non_negative_area():
    with pytest.raises(ValidationError):
        StructuralZone(
            id="z1",
            type=StructuralZoneType.CORE_SERVICE,
            polygon=[[0, 0], [10, 0], [10, 10]],
            story="s0",
            area_m2=-1,
        )


def test_forbidden_region_basic():
    fr = ForbiddenRegion(
        id="fr1",
        polygon=[[0, 0], [1, 0], [1, 1]],
        story="s0",
        reason=ForbiddenReason.ELEVATOR_SHAFT,
    )
    assert fr.reason == ForbiddenReason.ELEVATOR_SHAFT


def test_span_info_aspect_must_be_at_least_one():
    with pytest.raises(ValidationError):
        SpanInfo(
            bay_id="b1", span_x_mm=8000, span_y_mm=8000, aspect_ratio=0.5,
            classification="square", support_start="A-1", support_end="B-2",
        )


def test_span_map_defaults():
    sm = SpanMap()
    assert sm.spans == []
    assert sm.span_regularity == 1.0


def test_framing_zone_confidence_bounds():
    fz = FramingZone(
        zone_id="z1",
        primary_direction=FramingDirection.X_PRIMARY,
        secondary_direction=FramingDirection.Y_PRIMARY,
        confidence=0.75,
    )
    assert 0 <= fz.confidence <= 1


def test_gravity_system_candidate_plausibility_bounds():
    with pytest.raises(ValidationError):
        GravitySystemCandidate(
            system_type=GravitySystemType.RC_FLAT_SLAB, plausibility=2.0,
        )


def test_lateral_system_candidate_basic():
    lc = LateralSystemCandidate(
        system_type=LateralSystemType.CORE_WALL,
        zone_id="z1",
        plausibility=0.9,
    )
    assert lc.zone_id == "z1"


def test_constraint_priority_default_soft():
    c = StructuralConstraint(
        id="c1",
        type=ConstraintType.MAX_SPAN_LIMIT,
        value=12000,
    )
    assert c.priority == ConstraintPriority.SOFT


def test_vertical_group_quality_bounds():
    with pytest.raises(ValidationError):
        VerticalAlignmentGroup(
            id="v1", support_ids=["s1"], stories=["s0"], alignment_quality=1.5,
        )


def test_metadata_regularity_default():
    m = StructuralMetadata()
    assert m.building_regularity == "regular"


def test_full_graph_round_trip():
    """Full graph can be serialized and deserialized."""
    sdg = StructuralDesignGraph(
        building_graph_id="bg-1",
        zones=[StructuralZone(
            id="z1", type=StructuralZoneType.OPEN_FLOOR_PLATE,
            polygon=[[0, 0], [1, 0], [1, 1]], story="s0", area_m2=10,
        )],
        support_candidates=[SupportCandidate(
            id="s1", position=[0, 0], story="s0",
            classification=SupportCandidateClass.STRONG, score=0.9,
        )],
    )
    payload = sdg.model_dump(mode="json")
    restored = StructuralDesignGraph.model_validate(payload)
    assert restored.zones[0].id == "z1"
    assert restored.support_candidates[0].score == 0.9
