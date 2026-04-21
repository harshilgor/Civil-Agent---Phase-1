"""Tests for :func:`src.core.geometry.grid.infer_grid`."""

from __future__ import annotations

import pytest

from src.core.geometry.config import GridConfig
from src.core.geometry.grid import infer_grid

from .conftest import wall


class TestEmpty:
    def test_empty_walls_returns_empty_grid(self):
        g = infer_grid([], GridConfig())
        assert g.x_lines == []
        assert g.y_lines == []
        assert g.bays == []


class TestSingleAxis:
    def test_three_columns_yield_three_x_lines(self):
        # Three columns at X=0, 5000, 10000; each a 5m vertical wall.
        walls = [
            wall("c1a", (0.0, 0.0), (0.0, 5000.0)),
            wall("c1b", (0.0, 5000.0), (0.0, 10000.0)),
            wall("c1c", (0.0, 10000.0), (0.0, 15000.0)),
            wall("c2a", (5000.0, 0.0), (5000.0, 5000.0)),
            wall("c2b", (5000.0, 5000.0), (5000.0, 10000.0)),
            wall("c2c", (5000.0, 10000.0), (5000.0, 15000.0)),
            wall("c3a", (10000.0, 0.0), (10000.0, 5000.0)),
            wall("c3b", (10000.0, 5000.0), (10000.0, 10000.0)),
            wall("c3c", (10000.0, 10000.0), (10000.0, 15000.0)),
        ]
        g = infer_grid(walls, GridConfig())
        assert [line.id for line in g.x_lines] == ["A", "B", "C"]
        assert g.x_lines[0].position_mm == pytest.approx(0.0, abs=1.0)
        assert g.x_lines[2].position_mm == pytest.approx(10000.0, abs=1.0)

    def test_two_walls_not_enough_for_grid_line(self):
        # minimum_support_walls=3 → just two walls on a line shouldn't count.
        walls = [
            wall("a", (0.0, 0.0), (0.0, 5000.0)),
            wall("b", (0.0, 5000.0), (0.0, 10000.0)),
        ]
        g = infer_grid(walls, GridConfig())
        assert g.x_lines == []

    def test_support_length_floor(self):
        # Three vertical walls all on X=0 but each only 500mm long —
        # well below minimum_support_length_mm=2000.
        walls = [
            wall("a", (0.0, 0.0), (0.0, 500.0)),
            wall("b", (0.0, 600.0), (0.0, 1100.0)),
            wall("c", (0.0, 1200.0), (0.0, 1700.0)),
        ]
        g = infer_grid(walls, GridConfig())
        assert g.x_lines == []


class TestFullGrid:
    def test_three_by_three_grid_yields_four_bays(self):
        # 3×3 grid: X at 0/5000/10000, Y at 0/5000/10000. Walls along
        # each axis at each intersection create a proper grid.
        walls = []
        wid = 0
        for x in (0.0, 5000.0, 10000.0):
            for i in range(3):
                walls.append(
                    wall(
                        f"v_{wid}",
                        (x, i * 5000.0),
                        (x, (i + 1) * 5000.0),
                    )
                )
                wid += 1
        for y in (0.0, 5000.0, 10000.0):
            for i in range(3):
                walls.append(
                    wall(
                        f"h_{wid}",
                        (i * 5000.0, y),
                        ((i + 1) * 5000.0, y),
                    )
                )
                wid += 1

        g = infer_grid(walls, GridConfig())
        assert [line.id for line in g.x_lines] == ["A", "B", "C"]
        assert [line.id for line in g.y_lines] == ["1", "2", "3"]
        assert len(g.bays) == 4  # 2×2 bays between three grid lines
        bay_ids = {b.id for b in g.bays}
        assert {"A1", "A2", "B1", "B2"} == bay_ids
        for bay in g.bays:
            assert bay.span_x_mm == pytest.approx(5000.0, abs=1.0)
            assert bay.span_y_mm == pytest.approx(5000.0, abs=1.0)


class TestClustering:
    def test_near_parallel_walls_merge_into_single_line(self):
        # Three walls at X=0, two at X=150 (within 250mm cluster tol).
        # Centre should land around X=60.
        walls = [
            wall("a1", (0.0, 0.0), (0.0, 5000.0)),
            wall("a2", (0.0, 5000.0), (0.0, 10000.0)),
            wall("a3", (0.0, 10000.0), (0.0, 15000.0)),
            wall("b1", (150.0, 0.0), (150.0, 5000.0)),
            wall("b2", (150.0, 5000.0), (150.0, 10000.0)),
        ]
        g = infer_grid(walls, GridConfig())
        assert len(g.x_lines) == 1
        # Length-weighted mean of (0,0,0,150,150) = 60mm.
        assert g.x_lines[0].position_mm == pytest.approx(60.0, abs=1.0)
