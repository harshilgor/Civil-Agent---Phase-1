"""Tests for the CV preprocessor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.cv.preprocessor import Preprocessor


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Create a simple synthetic floor-plan-like image."""
    img = np.ones((800, 1000, 3), dtype=np.uint8) * 255
    # Draw some "walls"
    cv2.rectangle(img, (100, 100), (900, 700), (0, 0, 0), 5)
    cv2.line(img, (500, 100), (500, 700), (0, 0, 0), 5)
    cv2.line(img, (100, 400), (900, 400), (0, 0, 0), 5)
    path = tmp_path / "test_plan.png"
    cv2.imwrite(str(path), img)
    return path


class TestPreprocessor:
    def test_returns_all_keys(self, sample_image: Path):
        result = Preprocessor().preprocess(sample_image)
        assert "original" in result
        assert "gray" in result
        assert "binary" in result
        assert "color_clean" in result

    def test_binary_is_uint8(self, sample_image: Path):
        result = Preprocessor().preprocess(sample_image)
        assert result["binary"].dtype == np.uint8

    def test_gray_is_single_channel(self, sample_image: Path):
        result = Preprocessor().preprocess(sample_image)
        assert result["gray"].ndim == 2

    def test_resize(self, sample_image: Path):
        result = Preprocessor().preprocess(sample_image, target_size=(512, 512))
        assert result["original"].shape[:2] == (512, 512)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Preprocessor().preprocess("/nonexistent/file.png")
