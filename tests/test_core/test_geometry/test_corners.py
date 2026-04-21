"""Tests for :func:`src.core.geometry.corners.resolve_corners`."""

from __future__ import annotations

import pytest

from src.core.geometry.config import CornerConfig
from src.core.geometry.corners import resolve_corners

from .conftest import wall


class TestStubRemoval:
    def test_short_wall_dropped(self):
        walls = [
            wall("long", (0.0, 0.0), (5000.0, 0.0)),
            wall("stub", (2000.0, 0.0), (2050.0, 0.0)),
        ]
        out = resolve_corners(walls, CornerConfig(stub_wall_mm=150.0))
        ids = {w.id for w in out}
        assert "long" in ids
        assert "stub" not in ids

    def test_stub_just_above_threshold_is_kept(self):
        walls = [
            wall("tiny", (0.0, 0.0), (151.0, 0.0)),
        ]
        out = resolve_corners(walls, CornerConfig(stub_wall_mm=150.0))
        assert len(out) == 1


class TestEndpointExtension:
    def test_t_junction_stem_extends_to_crossbar(self):
        # Horizontal crossbar; vertical stem whose top misses by 30mm.
        walls = [
            wall("cross", (0.0, 3000.0), (5000.0, 3000.0)),
            wall("stem", (2500.0, 0.0), (2500.0, 2970.0)),
        ]
        out = resolve_corners(
            walls,
            CornerConfig(
                junction_radius_mm=150.0,
                stub_wall_mm=50.0,
                max_endpoint_shift_mm=100.0,
            ),
        )
        stem = next(w for w in out if w.id == "stem")
        # The near end (top, originally at y=2970) now sits on the crossbar.
        assert max(stem.start[1], stem.end[1]) == pytest.approx(3000.0, abs=1e-3)

    def test_extension_beyond_max_shift_is_skipped(self):
        # Stem misses by 200mm — beyond max_endpoint_shift_mm=100.
        walls = [
            wall("cross", (0.0, 3000.0), (5000.0, 3000.0)),
            wall("stem", (2500.0, 0.0), (2500.0, 2800.0)),
        ]
        out = resolve_corners(
            walls,
            CornerConfig(
                junction_radius_mm=300.0,
                stub_wall_mm=50.0,
                max_endpoint_shift_mm=100.0,
            ),
        )
        stem = next(w for w in out if w.id == "stem")
        assert max(stem.start[1], stem.end[1]) == pytest.approx(2800.0, abs=1.0)


class TestPerpendicularClip:
    def test_l_junction_both_short_clips_to_intersection(self):
        # Two walls meeting at an L corner but both short of (5000, 3000).
        walls = [
            wall("bottom", (0.0, 0.0), (4970.0, 0.0)),  # short 30mm
            wall("right", (5000.0, 30.0), (5000.0, 3000.0)),  # short 30mm
        ]
        out = resolve_corners(
            walls,
            CornerConfig(
                junction_radius_mm=150.0,
                stub_wall_mm=50.0,
                max_endpoint_shift_mm=200.0,
            ),
        )
        bottom = next(w for w in out if w.id == "bottom")
        right = next(w for w in out if w.id == "right")
        # Both endpoints should now agree on the corner.
        assert bottom.end == pytest.approx([5000.0, 0.0], abs=1.0)
        assert right.start == pytest.approx([5000.0, 0.0], abs=1.0)


class TestInvariants:
    def test_input_list_not_mutated(self, slightly_rotated_square):
        snapshot = [
            (w.start.copy(), w.end.copy()) for w in slightly_rotated_square
        ]
        resolve_corners(slightly_rotated_square, CornerConfig())
        for w, (s, e) in zip(slightly_rotated_square, snapshot):
            assert w.start == s
            assert w.end == e

    def test_empty_input_returns_empty(self):
        assert resolve_corners([], CornerConfig()) == []
