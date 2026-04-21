"""Tests for SupportCandidateGenerator and forbidden regions."""

from __future__ import annotations

from src.schema.structural_enums import (
    ForbiddenReason,
    SupportCandidateClass,
    SupportCandidateReason,
)
from src.structural.supports import SupportCandidateGenerator
from src.structural.zoner import StructuralZoner


def test_supports_generated_at_grid_intersections(office_tower_graph):
    gen = SupportCandidateGenerator()
    zones = StructuralZoner().classify(office_tower_graph)
    supports, _ = gen.generate(office_tower_graph, zones)
    grid_xs = {g.position_mm for g in office_tower_graph.grid.x_lines}
    grid_ys = {g.position_mm for g in office_tower_graph.grid.y_lines}
    found = 0
    for s in supports:
        if s.position[0] in grid_xs and s.position[1] in grid_ys:
            found += 1
    assert found >= 4, f"Expected grid intersections as candidates, got {found}"


def test_forbidden_region_from_elevator_core(office_tower_graph):
    gen = SupportCandidateGenerator()
    zones = StructuralZoner().classify(office_tower_graph)
    _, forbidden = gen.generate(office_tower_graph, zones)
    assert any(
        f.reason == ForbiddenReason.ELEVATOR_SHAFT for f in forbidden
    ), "Expected elevator shaft forbidden region"


def test_candidates_in_forbidden_are_marked_forbidden(office_tower_graph):
    gen = SupportCandidateGenerator()
    zones = StructuralZoner().classify(office_tower_graph)
    supports, _ = gen.generate(office_tower_graph, zones)
    forbidden_classed = [s for s in supports
                         if s.classification == SupportCandidateClass.FORBIDDEN]
    # At least the centre of the elevator core should be forbidden if any
    # candidate falls inside it.
    assert all(s.score == 0.0 for s in forbidden_classed)


def test_classification_thresholds(office_tower_graph):
    gen = SupportCandidateGenerator()
    zones = StructuralZoner().classify(office_tower_graph)
    supports, _ = gen.generate(office_tower_graph, zones)
    # Every support must have a valid classification
    valid = {SupportCandidateClass.STRONG, SupportCandidateClass.SECONDARY,
             SupportCandidateClass.WEAK, SupportCandidateClass.FORBIDDEN}
    assert all(s.classification in valid for s in supports)


def test_support_reasons_populated(office_tower_graph):
    gen = SupportCandidateGenerator()
    zones = StructuralZoner().classify(office_tower_graph)
    supports, _ = gen.generate(office_tower_graph, zones)
    reasons_union: set[SupportCandidateReason] = set()
    for s in supports:
        reasons_union.update(s.reasons)
    assert SupportCandidateReason.GRID_INTERSECTION in reasons_union
