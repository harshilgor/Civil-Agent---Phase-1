"""End-to-end integration test for the Structural Abstraction Engine."""

from __future__ import annotations

from src.schema.structural_graph import StructuralDesignGraph
from src.structural.engine import StructuralEngine


def test_engine_produces_full_graph(office_tower_graph):
    engine = StructuralEngine()
    sdg = engine.build(office_tower_graph, graph_id="test-1")
    assert isinstance(sdg, StructuralDesignGraph)
    assert sdg.building_graph_id == "test-1"
    assert sdg.zones, "Zones populated"
    assert sdg.support_candidates, "Supports populated"
    assert sdg.forbidden_regions, "Forbidden regions populated"
    assert sdg.span_map.spans, "Span map populated"
    assert sdg.framing_zones, "Framing zones populated"
    assert sdg.gravity_system_candidates, "Gravity candidates populated"
    assert sdg.lateral_system_candidates, "Lateral candidates populated"
    assert sdg.constraints, "Constraints populated"
    assert sdg.metadata.processing_time_seconds > 0
    assert 0 <= sdg.metadata.confidence_overall <= 1


def test_engine_idempotent(office_tower_graph):
    engine = StructuralEngine()
    sdg1 = engine.build(office_tower_graph)
    sdg2 = engine.build(office_tower_graph)
    # Deterministic: same counts
    assert len(sdg1.zones) == len(sdg2.zones)
    assert len(sdg1.support_candidates) == len(sdg2.support_candidates)
    assert len(sdg1.constraints) == len(sdg2.constraints)


def test_engine_handles_minimal_graph(sample_building_graph):
    """Baseline graph has no cores and minimal rooms — should not crash."""
    engine = StructuralEngine()
    sdg = engine.build(sample_building_graph)
    assert isinstance(sdg, StructuralDesignGraph)
    assert sdg.metadata.processing_time_seconds >= 0


def test_engine_round_trip_serialization(office_tower_graph):
    engine = StructuralEngine()
    sdg = engine.build(office_tower_graph)
    payload = sdg.model_dump(mode="json")
    restored = StructuralDesignGraph.model_validate(payload)
    assert len(restored.zones) == len(sdg.zones)
    assert len(restored.support_candidates) == len(sdg.support_candidates)
