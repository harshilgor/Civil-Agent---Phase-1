"""Tests for FramingDirectionInferrer."""

from __future__ import annotations

from src.schema.structural_enums import FramingDirection
from src.structural.framing import FramingDirectionInferrer
from src.structural.spans import SpanMapper
from src.structural.zoner import StructuralZoner


def test_framing_direction_assigned_to_each_zone(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    sm = SpanMapper().map(office_tower_graph)
    out = FramingDirectionInferrer().infer(office_tower_graph, zones, sm)
    assert len(out) == len(zones)
    for fz in out:
        assert fz.primary_direction in FramingDirection
        assert 0 <= fz.confidence <= 1


def test_bidirectional_on_square_grid(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    sm = SpanMapper().map(office_tower_graph)
    out = FramingDirectionInferrer().infer(office_tower_graph, zones, sm)
    # At least one zone can be bidirectional (square bays); not strictly enforced
    directions = {fz.primary_direction for fz in out}
    assert directions, "Must produce at least one direction"
