"""Tests for :func:`src.core.geometry.snap.snap_orthogonal`."""

from __future__ import annotations

import math

import pytest

from src.core.geometry.config import SnapConfig
from src.core.geometry.snap import snap_orthogonal

from .conftest import wall


class TestAngleSnap:
    def test_already_axis_aligned_is_unchanged(self, square_room_walls):
        out = snap_orthogonal(square_room_walls, SnapConfig())
        # Exact geometry round-trips (within float noise).
        for original, result in zip(square_room_walls, out):
            assert result.start == pytest.approx(original.start, abs=1e-6)
            assert result.end == pytest.approx(original.end, abs=1e-6)

    def test_slightly_rotated_wall_becomes_axis_aligned(self):
        # A 5m wall tilted by 0.3°.
        tilted = [wall("w", (0.0, 10.0), (5000.0, -10.0))]
        out = snap_orthogonal(tilted, SnapConfig())
        # Both endpoints now share the same Y.
        assert out[0].start[1] == pytest.approx(out[0].end[1], abs=1e-6)
        # Length is preserved to within a millimetre.
        dx = out[0].end[0] - out[0].start[0]
        dy = out[0].end[1] - out[0].start[1]
        assert math.hypot(dx, dy) == pytest.approx(5000.0, abs=1.0)

    def test_diagonal_is_preserved_by_default(self):
        diagonal = [wall("w", (0.0, 0.0), (5000.0, 5000.0))]
        out = snap_orthogonal(diagonal, SnapConfig())
        assert out[0].start == [0.0, 0.0]
        assert out[0].end == [5000.0, 5000.0]

    def test_diagonal_is_snapped_when_preserve_diagonals_false(self):
        diagonal = [wall("w", (0.0, 0.0), (5000.0, 5000.0))]
        cfg = SnapConfig(preserve_diagonals=False)
        out = snap_orthogonal(diagonal, cfg)
        # 45° is equidistant from 0° and 90°; our tie-breaker picks 0°.
        assert out[0].start[1] == pytest.approx(out[0].end[1], abs=1e-6)


class TestAxisClustering:
    def test_two_near_parallel_walls_collapse_onto_same_rail(self):
        # Two vertical walls at X=4990 and X=5010 (within 75mm cluster).
        walls = [
            wall("a", (4990.0, 0.0), (4990.0, 3000.0)),
            wall("b", (5010.0, 0.0), (5010.0, 3000.0)),
        ]
        out = snap_orthogonal(walls, SnapConfig())
        xs = [w.start[0] for w in out] + [w.end[0] for w in out]
        assert max(xs) - min(xs) < 1e-6

    def test_far_apart_rails_are_left_alone(self):
        walls = [
            wall("a", (0.0, 0.0), (0.0, 3000.0)),
            wall("b", (5000.0, 0.0), (5000.0, 3000.0)),
        ]
        out = snap_orthogonal(walls, SnapConfig())
        assert out[0].start[0] == 0.0
        assert out[1].start[0] == 5000.0


class TestEndpointWeld:
    def test_close_endpoints_collapse(self):
        # Two walls meeting at a near-corner with a 20mm gap.
        walls = [
            wall("a", (0.0, 0.0), (5000.0, 0.0)),        # horizontal
            wall("b", (5020.0, 0.0), (5020.0, 3000.0)),  # vertical 20mm off
        ]
        out = snap_orthogonal(walls, SnapConfig())
        # The gap should close — second wall's bottom is now at x=5000.
        # (Subject to cluster-center being the mean of 5000 and 5020.)
        gap_start = out[1].start[0]
        first_end = out[0].end[0]
        assert gap_start == pytest.approx(first_end, abs=1e-3)

    def test_far_endpoints_are_not_welded(self):
        # Gap of 200mm is well beyond endpoint_weld_mm=50.
        walls = [
            wall("a", (0.0, 0.0), (5000.0, 0.0)),
            wall("b", (5200.0, 0.0), (5200.0, 3000.0)),
        ]
        out = snap_orthogonal(walls, SnapConfig())
        assert abs(out[1].start[0] - out[0].end[0]) > 100.0


class TestRoundTrip:
    def test_rotated_room_becomes_clean_square(self, slightly_rotated_square):
        out = snap_orthogonal(slightly_rotated_square, SnapConfig())
        # Every wall should now be axis-aligned.
        for w in out:
            x_same = abs(w.start[0] - w.end[0]) < 1.0
            y_same = abs(w.start[1] - w.end[1]) < 1.0
            assert x_same or y_same, f"{w.id} is not axis-aligned after snap"

    def test_input_is_not_mutated(self, slightly_rotated_square):
        snapshot = [
            (w.start.copy(), w.end.copy()) for w in slightly_rotated_square
        ]
        snap_orthogonal(slightly_rotated_square, SnapConfig())
        for w, (s, e) in zip(slightly_rotated_square, snapshot):
            assert w.start == s
            assert w.end == e
