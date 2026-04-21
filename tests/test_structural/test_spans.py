"""Tests for SpanMapper."""

from __future__ import annotations

from src.structural.spans import SpanMapper


def test_regular_grid_produces_high_regularity(office_tower_graph):
    sm = SpanMapper().map(office_tower_graph)
    assert sm.span_regularity > 0.9, f"Regular grid should be regular, got {sm.span_regularity}"
    assert sm.max_span_mm > 0
    assert sm.typical_span_mm > 0


def test_span_classification_square(office_tower_graph):
    sm = SpanMapper().map(office_tower_graph)
    assert any(s.classification == "square" for s in sm.spans)


def test_aspect_ratio_always_at_least_one(office_tower_graph):
    sm = SpanMapper().map(office_tower_graph)
    for s in sm.spans:
        assert s.aspect_ratio >= 1.0 - 1e-9
