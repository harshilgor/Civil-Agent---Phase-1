"""Tests for :func:`src.core.geometry.columns.score_columns`."""

from __future__ import annotations

import pytest

from src.core.geometry.columns import score_columns
from src.core.geometry.config import ColumnConfig
from src.schema.building_graph import (
    Bay,
    ColumnCandidate,
    GridLine,
    GridSystem,
)

from .conftest import wall


def _grid_3x3() -> GridSystem:
    x_lines = [
        GridLine(id="A", position_mm=0.0),
        GridLine(id="B", position_mm=5000.0),
        GridLine(id="C", position_mm=10000.0),
    ]
    y_lines = [
        GridLine(id="1", position_mm=0.0),
        GridLine(id="2", position_mm=5000.0),
        GridLine(id="3", position_mm=10000.0),
    ]
    bays = [
        Bay(
            id="A1",
            span_x_mm=5000.0,
            span_y_mm=5000.0,
            grid_x_start="A",
            grid_x_end="B",
            grid_y_start="1",
            grid_y_end="2",
        )
    ]
    return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays)


class TestEmptyInputs:
    def test_no_grid_returns_empty(self):
        out = score_columns([], GridSystem(x_lines=[], y_lines=[], bays=[]), ColumnConfig())
        assert out == []


class TestEndpointSignal:
    def test_grid_intersection_with_two_endpoints_is_emitted(self):
        # Walls converge on (5000, 5000) — the B2 grid intersection.
        walls = [
            wall("n", (5000.0, 5000.0), (5000.0, 10000.0)),
            wall("e", (5000.0, 5000.0), (10000.0, 5000.0)),
        ]
        grid = _grid_3x3()
        out = score_columns(walls, grid, ColumnConfig())
        ids = {c.grid_intersection for c in out}
        assert "B2" in ids

    def test_score_below_threshold_is_filtered(self):
        walls = []  # Nothing to contribute — score is 0.
        grid = _grid_3x3()
        out = score_columns(walls, grid, ColumnConfig(required_score=0.1))
        assert out == []


class TestShortWallSignal:
    def test_short_wall_near_intersection_contributes(self):
        # 300mm stub near (0, 0) — below short_wall_max_mm=500.
        walls = [wall("stub", (0.0, 0.0), (300.0, 0.0))]
        grid = _grid_3x3()
        out = score_columns(
            walls,
            grid,
            ColumnConfig(required_score=0.3),
        )
        ids = {c.grid_intersection for c in out}
        assert "A1" in ids


class TestCadSignal:
    def test_cad_column_within_promotion_radius_is_required(self):
        cad = [
            ColumnCandidate(
                position=[5000.0, 5000.0],
                is_required=False,
                confidence=1.0,
            )
        ]
        grid = _grid_3x3()
        out = score_columns([], grid, ColumnConfig(), cad_columns=cad)
        b2 = next((c for c in out if c.grid_intersection == "B2"), None)
        assert b2 is not None
        assert b2.is_required is True
        assert "CAD-matched" in (b2.notes or "")

    def test_cad_column_far_from_any_intersection_contributes_nothing(self):
        cad = [
            ColumnCandidate(
                position=[20000.0, 20000.0],  # way off any grid line
                is_required=False,
                confidence=1.0,
            )
        ]
        grid = _grid_3x3()
        out = score_columns([], grid, ColumnConfig(), cad_columns=cad)
        assert out == []

    def test_cad_signal_alone_crosses_threshold(self):
        """The default signal_weights.cad_column=1.0 should let a CAD
        match alone cross required_score=0.5 without any wall or stub
        evidence."""

        cad = [
            ColumnCandidate(
                position=[5000.0, 5000.0],
                is_required=False,
                confidence=1.0,
            )
        ]
        grid = _grid_3x3()
        out = score_columns([], grid, ColumnConfig(), cad_columns=cad)
        assert any(c.grid_intersection == "B2" for c in out)


class TestScoreBounds:
    def test_combined_signals_clamped_to_one(self):
        # Walls + stub + CAD all converge — combined weight > 1.
        walls = [
            wall("stub", (4999.0, 5000.0), (5100.0, 5000.0)),
            wall("n", (5000.0, 5000.0), (5000.0, 10000.0)),
            wall("e", (5000.0, 5000.0), (10000.0, 5000.0)),
        ]
        cad = [
            ColumnCandidate(
                position=[5000.0, 5000.0], is_required=False, confidence=1.0
            )
        ]
        grid = _grid_3x3()
        out = score_columns(walls, grid, ColumnConfig(), cad_columns=cad)
        b2 = next(c for c in out if c.grid_intersection == "B2")
        assert 0.0 <= b2.confidence <= 1.0
