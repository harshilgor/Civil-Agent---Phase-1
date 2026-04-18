"""Tests for ConstraintCompiler."""

from __future__ import annotations

from src.schema.structural_enums import ConstraintPriority, ConstraintType
from src.structural.constraints import ConstraintCompiler
from src.structural.lateral import LateralSystemCandidateGenerator
from src.structural.spans import SpanMapper
from src.structural.supports import SupportCandidateGenerator
from src.structural.vertical import VerticalContinuityAnalyzer
from src.structural.zoner import StructuralZoner


def _run_up_to_constraints(graph):
    zones = StructuralZoner().classify(graph)
    supports, forbidden = SupportCandidateGenerator().generate(graph, zones)
    supports, vgroups = VerticalContinuityAnalyzer().analyze(supports, graph)
    sm = SpanMapper().map(graph)
    lateral = LateralSystemCandidateGenerator().generate(graph, zones)
    constraints = ConstraintCompiler().compile(
        graph=graph,
        zones=zones,
        support_candidates=supports,
        forbidden_regions=forbidden,
        vertical_groups=vgroups,
        span_map=sm,
        lateral_candidates=lateral,
    )
    return constraints


def test_produces_no_support_zone_constraints(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    types = [c.type for c in cs]
    assert ConstraintType.NO_SUPPORT_ZONE in types


def test_produces_required_support_constraints(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    types = [c.type for c in cs]
    # Should have at least one REQUIRED_SUPPORT from stacked strong candidates
    assert ConstraintType.REQUIRED_SUPPORT in types


def test_max_span_limit_is_hard(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    max_span_cs = [c for c in cs if c.type == ConstraintType.MAX_SPAN_LIMIT]
    assert max_span_cs
    assert all(c.priority == ConstraintPriority.HARD for c in max_span_cs)


def test_lateral_requirement_constraint_present(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    types = [c.type for c in cs]
    assert ConstraintType.LATERAL_SYSTEM_REQUIRED in types


def test_core_continuity_constraints_generated(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    types = [c.type for c in cs]
    assert ConstraintType.CORE_CONTINUITY in types


def test_opening_avoidance_for_wide_openings(office_tower_graph):
    cs = _run_up_to_constraints(office_tower_graph)
    types = [c.type for c in cs]
    assert ConstraintType.OPENING_AVOIDANCE in types
