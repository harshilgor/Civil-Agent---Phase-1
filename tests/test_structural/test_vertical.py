"""Tests for VerticalContinuityAnalyzer."""

from __future__ import annotations

from src.schema.structural_enums import SupportCandidateClass
from src.structural.supports import SupportCandidateGenerator
from src.structural.vertical import VerticalContinuityAnalyzer
from src.structural.zoner import StructuralZoner


def test_vertical_groups_detected_for_stacked_grid(office_tower_graph):
    zoner = StructuralZoner()
    zones = zoner.classify(office_tower_graph)
    gen = SupportCandidateGenerator()
    supports, _ = gen.generate(office_tower_graph, zones)
    _, groups = VerticalContinuityAnalyzer().analyze(supports, office_tower_graph)
    # We have 3 stories × regular grid; expect several stacks
    assert groups, "Expected at least one vertical alignment group"
    perfect = [g for g in groups if len(g.stories) == 3]
    assert perfect, "Expected fully stacked groups for a regular grid tower"


def test_stacked_supports_get_bonus(office_tower_graph):
    zoner = StructuralZoner()
    zones = zoner.classify(office_tower_graph)
    gen = SupportCandidateGenerator()
    supports_before, _ = gen.generate(office_tower_graph, zones)
    pre_scores = {s.id: s.score for s in supports_before}
    supports_after, _ = VerticalContinuityAnalyzer().analyze(
        list(supports_before), office_tower_graph,
    )
    stacked = [s for s in supports_after if s.is_stacked]
    assert stacked, "Expected some supports to be marked stacked"
    for s in stacked:
        assert s.score >= pre_scores[s.id] - 1e-6


def test_classification_updated_after_bonus(office_tower_graph):
    zoner = StructuralZoner()
    zones = zoner.classify(office_tower_graph)
    gen = SupportCandidateGenerator()
    supports, _ = gen.generate(office_tower_graph, zones)
    supports, _ = VerticalContinuityAnalyzer().analyze(supports, office_tower_graph)
    # Classifications must remain valid
    valid = {SupportCandidateClass.STRONG, SupportCandidateClass.SECONDARY,
             SupportCandidateClass.WEAK, SupportCandidateClass.FORBIDDEN}
    assert all(s.classification in valid for s in supports)
