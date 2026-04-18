"""Tests for GravitySystemEligibilityEvaluator."""

from __future__ import annotations

from src.schema.enums import MaterialPreference
from src.schema.structural_enums import GravitySystemType
from src.structural.gravity import GravitySystemEligibilityEvaluator
from src.structural.spans import SpanMapper


def test_gravity_produces_candidates(office_tower_graph):
    sm = SpanMapper().map(office_tower_graph)
    candidates = GravitySystemEligibilityEvaluator().evaluate(office_tower_graph, sm)
    assert candidates, "Expected RC gravity system candidates"
    types = {c.system_type for c in candidates}
    assert GravitySystemType.RC_FLAT_SLAB in types
    assert GravitySystemType.RC_BEAM_SLAB in types


def test_gravity_sorted_by_plausibility(office_tower_graph):
    sm = SpanMapper().map(office_tower_graph)
    candidates = GravitySystemEligibilityEvaluator().evaluate(office_tower_graph, sm)
    plaus = [c.plausibility for c in candidates]
    assert plaus == sorted(plaus, reverse=True)


def test_steel_material_suppresses_rc_candidates(office_tower_graph):
    office_tower_graph = office_tower_graph.model_copy(
        update={"project": office_tower_graph.project.model_copy(
            update={"material_preference": MaterialPreference.STRUCTURAL_STEEL}
        )}
    )
    sm = SpanMapper().map(office_tower_graph)
    candidates = GravitySystemEligibilityEvaluator().evaluate(office_tower_graph, sm)
    assert candidates == [], "Steel material should suppress RC-only V1 candidates"
