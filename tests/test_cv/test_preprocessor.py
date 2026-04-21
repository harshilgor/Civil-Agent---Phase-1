"""Tests for the CV preprocessor."""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from src.cv.preprocessor import Preprocessor, VlmImagePayload


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


# ---------------------------------------------------------------------------
# Stage 1 — prepare_for_vlm
# ---------------------------------------------------------------------------


@pytest.fixture()
def small_floor_plan_png(tmp_path: Path) -> Path:
    """A ~2000 px wide synthetic plan.  Used to exercise the downscale
    path in :meth:`Preprocessor.prepare_for_vlm`.
    """
    img = Image.new("RGB", (2400, 1800), color=(255, 255, 255))
    path = tmp_path / "large_plan.png"
    img.save(path, format="PNG", dpi=(300, 300))
    return path


class TestPrepareForVlm:
    def test_returns_vlm_image_payload(self, sample_image: Path):
        payload = Preprocessor().prepare_for_vlm(sample_image)
        assert isinstance(payload, VlmImagePayload)
        assert payload.png_bytes.startswith(b"\x89PNG\r\n")
        assert payload.width > 0 and payload.height > 0

    def test_small_image_not_downscaled(self, sample_image: Path):
        payload = Preprocessor().prepare_for_vlm(sample_image)
        # Fixture is 1000×800 — well under the 1568-px cap.
        assert payload.was_downscaled is False
        assert (payload.width, payload.height) == (
            payload.original_width,
            payload.original_height,
        )

    def test_large_image_is_downscaled(self, small_floor_plan_png: Path):
        payload = Preprocessor().prepare_for_vlm(small_floor_plan_png)
        assert payload.was_downscaled is True
        assert max(payload.width, payload.height) <= 1568
        # Original dimensions are preserved on the payload for audit.
        assert payload.original_width == 2400
        assert payload.original_height == 1800

    def test_dpi_from_metadata(self, small_floor_plan_png: Path):
        payload = Preprocessor().prepare_for_vlm(small_floor_plan_png)
        # PIL round-trips DPI as a float and may drift by <1 due to the
        # png chunk's integer-ratio representation; assert the vicinity.
        assert payload.dpi == pytest.approx(300.0, abs=0.01)
        assert payload.dpi_source == "exif"

    def test_dpi_fallback_when_metadata_missing(self, tmp_path: Path):
        img = Image.new("RGB", (300, 300), color=(255, 255, 255))
        path = tmp_path / "no_dpi.png"
        img.save(path, format="PNG")  # no dpi metadata
        payload = Preprocessor().prepare_for_vlm(path)
        assert payload.dpi_source == "fallback"
        assert payload.dpi == 150.0

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Preprocessor().prepare_for_vlm("/nonexistent/file.png")

    def test_png_round_trippable(self, sample_image: Path):
        """The returned bytes must be a valid PNG that PIL can re-open."""
        payload = Preprocessor().prepare_for_vlm(sample_image)
        reopened = Image.open(io.BytesIO(payload.png_bytes))
        assert reopened.mode in {"RGB", "RGBA"}
        assert reopened.size == (payload.width, payload.height)

    def test_exif_rotation_applied(self, tmp_path: Path):
        """Simulate a JPEG whose EXIF Orientation=6 tag says 'rotate 90 CW'.
        ``ImageOps.exif_transpose`` must flip width/height, and the
        payload must record that rotation was applied."""
        landscape = Image.new("RGB", (1000, 600), color=(200, 220, 240))
        path = tmp_path / "rotated.jpg"
        exif = landscape.getexif()
        exif[274] = 6  # 274 = Orientation; 6 = Rotate 90 CW on open
        landscape.save(path, format="JPEG", exif=exif)

        payload = Preprocessor().prepare_for_vlm(path)
        # Orientation=6 flips w/h: the 1000×600 landscape becomes
        # 600×1000 portrait after ImageOps.exif_transpose.
        assert payload.was_rotated is True
        assert payload.original_width == 600
        assert payload.original_height == 1000

    def test_respects_custom_max_edge(self, small_floor_plan_png: Path):
        payload = Preprocessor().prepare_for_vlm(
            small_floor_plan_png, max_edge_px=800
        )
        assert max(payload.width, payload.height) <= 800

    def test_does_not_mutate_source_file_for_stage3(
        self, small_floor_plan_png: Path
    ):
        """Regression: the VLM path must not touch the source file on disk.

        Stage 3's U-Net / YOLO-Seg path re-reads the original upload at
        full resolution via :meth:`Preprocessor.preprocess`; if
        :meth:`prepare_for_vlm` rewrote the file (e.g. by saving the
        downscaled PNG back to ``image_path``) the segmenter would
        silently consume the 1568-px downsample and produce lower-quality
        masks.  Confirmed here by asserting:

        1. The on-disk file is byte-identical after ``prepare_for_vlm``.
        2. ``preprocess(path)`` returns the original 2400x1800 buffer
           (not the 1568-capped VLM payload dimensions).
        """
        pre = Preprocessor()

        original_bytes = small_floor_plan_png.read_bytes()
        payload = pre.prepare_for_vlm(small_floor_plan_png)
        assert payload.was_downscaled is True  # fixture is > 1568 px
        assert small_floor_plan_png.read_bytes() == original_bytes

        full_res = pre.preprocess(small_floor_plan_png)
        h, w = full_res["original"].shape[:2]
        assert (w, h) == (2400, 1800)
        # And the VLM payload is demonstrably smaller than what Stage 3
        # sees, so the two paths are not pointing at the same buffer.
        assert max(payload.width, payload.height) <= 1568
        assert max(w, h) > 1568
