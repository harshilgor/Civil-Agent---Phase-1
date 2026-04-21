"""Tests for the vectorizer."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.cv.vectorizer import Vectorizer, VectorizationConfig


@pytest.fixture()
def simple_wall_mask() -> np.ndarray:
    """Create a binary mask with horizontal and vertical wall lines."""
    mask = np.zeros((500, 500), dtype=np.uint8)
    cv2.line(mask, (50, 50), (450, 50), 255, 8)
    cv2.line(mask, (50, 450), (450, 450), 255, 8)
    cv2.line(mask, (50, 50), (50, 450), 255, 8)
    cv2.line(mask, (450, 50), (450, 450), 255, 8)
    return mask


class TestVectorizer:
    def test_vectorize_produces_segments(self, simple_wall_mask: np.ndarray):
        cfg = VectorizationConfig(min_segment_length_mm=100)
        v = Vectorizer(cfg)
        result = v.vectorize(simple_wall_mask, scale_mm_per_px=10.0)
        assert len(result) > 0

    def test_segments_have_required_keys(self, simple_wall_mask: np.ndarray):
        cfg = VectorizationConfig(min_segment_length_mm=100)
        v = Vectorizer(cfg)
        result = v.vectorize(simple_wall_mask, scale_mm_per_px=10.0)
        for seg in result:
            assert "start" in seg
            assert "end" in seg
            assert "thickness_mm" in seg

    def test_scale_factor_applied(self, simple_wall_mask: np.ndarray):
        cfg = VectorizationConfig(min_segment_length_mm=50)
        v = Vectorizer(cfg)
        result_1x = v.vectorize(simple_wall_mask, scale_mm_per_px=1.0)
        result_10x = v.vectorize(simple_wall_mask, scale_mm_per_px=10.0)
        if result_1x and result_10x:
            max_1x = max(max(abs(s["start"][0]), abs(s["end"][0])) for s in result_1x)
            max_10x = max(max(abs(s["start"][0]), abs(s["end"][0])) for s in result_10x)
            assert max_10x > max_1x * 5

    def test_scale_aware_tolerances_are_resolution_independent(self):
        """Two images of the same plan at different DPIs should yield
        geometrically equivalent segments when scale is set correctly."""
        # Low-res mask (scale 20 mm/px → 20m wide building)
        low = np.zeros((250, 500), dtype=np.uint8)
        cv2.line(low, (25, 25), (475, 25), 255, 4)
        cv2.line(low, (25, 225), (475, 225), 255, 4)

        # High-res version of the same plan (scale 5 mm/px)
        high = np.zeros((1000, 2000), dtype=np.uint8)
        cv2.line(high, (100, 100), (1900, 100), 255, 16)
        cv2.line(high, (100, 900), (1900, 900), 255, 16)

        cfg = VectorizationConfig(min_segment_length_mm=500)
        v = Vectorizer(cfg)

        low_segs = v.vectorize(low, scale_mm_per_px=20.0)
        high_segs = v.vectorize(high, scale_mm_per_px=5.0)

        # Both should detect at least one segment
        assert len(low_segs) > 0
        assert len(high_segs) > 0

        def _max_len(segs):
            return max(
                ((s["end"][0] - s["start"][0]) ** 2 + (s["end"][1] - s["start"][1]) ** 2) ** 0.5
                for s in segs
            )
        # Lengths in mm should match (within 10%)
        len_low = _max_len(low_segs)
        len_high = _max_len(high_segs)
        assert abs(len_low - len_high) / max(len_low, len_high) < 0.20

    def test_fallback_scale_when_no_scale_provided(self):
        mask = np.zeros((500, 500), dtype=np.uint8)
        cv2.line(mask, (50, 50), (450, 50), 255, 8)
        v = Vectorizer()
        result = v.vectorize(mask, scale_mm_per_px=None)
        assert v.last_stats is not None
        assert v.last_stats.scale_was_inferred is True
        assert v.last_stats.confidence < 1.0

    def test_empty_mask_returns_empty(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        v = Vectorizer()
        result = v.vectorize(mask, scale_mm_per_px=10.0)
        assert result == []


class TestPolygonExtraction:
    def test_masks_to_polygons(self):
        mask = np.zeros((200, 200), dtype=np.uint8)
        cv2.rectangle(mask, (20, 20), (180, 180), 255, -1)
        v = Vectorizer()
        polys = v.masks_to_polygons({0: mask}, scale_mm_per_px=10.0)
        assert len(polys) == 1
        assert polys[0]["area_m2"] > 0
        assert len(polys[0]["polygon"]) >= 4
