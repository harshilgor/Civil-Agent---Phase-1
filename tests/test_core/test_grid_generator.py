"""Tests for GridGenerator."""

from __future__ import annotations

import pytest

from src.core.grid_generator import GridGenerator


@pytest.fixture()
def gen() -> GridGenerator:
    return GridGenerator()


class TestBasicGrid:
    def test_single_bay(self, gen: GridGenerator):
        grid = gen.generate(length_mm=6000, width_mm=6000)
        assert len(grid.x_lines) >= 2
        assert len(grid.y_lines) >= 2
        assert grid.x_lines[0].position_mm == 0
        assert grid.x_lines[-1].position_mm == 6000

    def test_regular_grid_4x3(self, gen: GridGenerator):
        grid = gen.generate(
            length_mm=32000,
            width_mm=24000,
            preferred_bay_x_mm=8000,
            preferred_bay_y_mm=8000,
        )
        assert len(grid.x_lines) == 5  # 0, 8k, 16k, 24k, 32k
        assert len(grid.y_lines) == 4  # 0, 8k, 16k, 24k
        assert len(grid.bays) == 4 * 3  # 4 x-bays × 3 y-bays

    def test_grid_line_labels(self, gen: GridGenerator):
        grid = gen.generate(length_mm=24000, width_mm=16000, preferred_bay_x_mm=8000)
        x_ids = [gl.id for gl in grid.x_lines]
        assert x_ids[0] == "A"
        assert x_ids[-1] == "D"
        y_ids = [gl.id for gl in grid.y_lines]
        assert y_ids[0] == "1"

    def test_grid_lines_ascending(self, gen: GridGenerator):
        grid = gen.generate(length_mm=50000, width_mm=30000)
        x_pos = [gl.position_mm for gl in grid.x_lines]
        assert x_pos == sorted(x_pos)
        y_pos = [gl.position_mm for gl in grid.y_lines]
        assert y_pos == sorted(y_pos)

    def test_bay_spans_positive(self, gen: GridGenerator):
        grid = gen.generate(length_mm=40000, width_mm=20000)
        for bay in grid.bays:
            assert bay.span_x_mm > 0
            assert bay.span_y_mm > 0


class TestBaySizeClamping:
    def test_too_small_bay_gets_clamped(self, gen: GridGenerator):
        grid = gen.generate(
            length_mm=6000, width_mm=6000,
            preferred_bay_x_mm=2000, min_bay_mm=4000, max_bay_mm=15000,
        )
        for bay in grid.bays:
            assert bay.span_x_mm >= 4000 or len(grid.x_lines) == 2

    def test_too_large_bay_gets_split(self, gen: GridGenerator):
        grid = gen.generate(
            length_mm=40000, width_mm=10000,
            preferred_bay_x_mm=40000, min_bay_mm=4000, max_bay_mm=12000,
        )
        for bay in grid.bays:
            assert bay.span_x_mm <= 12000 + 1  # +1 for rounding


class TestConstraints:
    def test_constraint_adds_grid_line(self, gen: GridGenerator):
        grid = gen.generate(
            length_mm=32000, width_mm=24000,
            preferred_bay_x_mm=8000,
            x_constraints=[12000],
        )
        x_positions = {gl.position_mm for gl in grid.x_lines}
        assert 12000 in x_positions

    def test_constraint_near_existing_merges(self):
        gen = GridGenerator(merge_tolerance_mm=500)
        grid = gen.generate(
            length_mm=16000, width_mm=8000,
            preferred_bay_x_mm=8000,
            x_constraints=[8200],  # within 500 of 8000
        )
        x_positions = [gl.position_mm for gl in grid.x_lines]
        assert 8200 in x_positions
        assert 8000 not in x_positions

    def test_out_of_range_constraint_ignored(self, gen: GridGenerator):
        grid = gen.generate(
            length_mm=16000, width_mm=8000,
            x_constraints=[99999],
        )
        x_positions = {gl.position_mm for gl in grid.x_lines}
        assert 99999 not in x_positions


class TestEdgeCases:
    def test_very_small_building(self, gen: GridGenerator):
        grid = gen.generate(length_mm=4000, width_mm=4000, min_bay_mm=3000)
        assert len(grid.x_lines) >= 2
        assert len(grid.bays) >= 1

    def test_very_long_narrow_building(self, gen: GridGenerator):
        grid = gen.generate(length_mm=100000, width_mm=8000)
        assert len(grid.x_lines) > len(grid.y_lines)
