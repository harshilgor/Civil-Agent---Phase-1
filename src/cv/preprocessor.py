"""Floor-plan image preprocessing.

Handles PDF→image conversion, deskewing, adaptive thresholding,
morphological cleanup, and noise removal.  Also exposes
:meth:`Preprocessor.prepare_for_vlm` — the Stage-1 entry point that
normalises an upload for Stage-2 VLM classification (EXIF orientation,
DPI-aware sizing, bounded PNG encoding).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import structlog
from PIL import Image, ImageOps

logger = structlog.get_logger(__name__)

_PDF_DPI = 300

# Claude's vision API accepts up to ~8000 px per side and ~5 MB per image,
# but classification-grade crops do not need that much detail.  We cap the
# longest edge at 1568 px — Anthropic's recommended value — so the VLM
# sees the full plan with minimal bandwidth.
_VLM_MAX_EDGE_PX = 1568
_VLM_MAX_BYTES = 5 * 1024 * 1024
# If EXIF / PDF metadata is silent, assume the scan was 150 DPI — that's
# the most common default for architectural plans rendered to raster.
_VLM_FALLBACK_DPI = 150.0


@dataclass(frozen=True)
class VlmImagePayload:
    """The output of :meth:`Preprocessor.prepare_for_vlm`.

    Kept deliberately small: everything Stage 2 needs to send Claude a
    classification request, plus the metadata Stage 3+ will want when
    the real detector runs against the same pixel buffer.
    """

    png_bytes: bytes
    width: int
    height: int
    original_width: int
    original_height: int
    dpi: float
    dpi_source: str  # "exif" | "pdf" | "fallback"
    was_rotated: bool
    was_downscaled: bool


class Preprocessor:
    """Clean and normalise a floor-plan image for downstream CV models."""

    def preprocess(
        self,
        image_path: str | Path,
        target_size: tuple[int, int] | None = None,
    ) -> dict[str, np.ndarray]:
        """Load, clean, and return processed images.

        Returns a dict with keys:
        - ``original``: the original colour image (BGR)
        - ``gray``: grayscale version
        - ``binary``: adaptive-thresholded + cleaned binary mask
        - ``color_clean``: colour image after deskew (for overlay display)

        If *target_size* is given as ``(width, height)``, images are resized.
        """
        image_path = Path(image_path)
        color_img = self._load_image(image_path)
        gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)

        # Deskew
        angle = self._detect_skew(gray)
        if abs(angle) > 0.5:
            color_img = self._rotate(color_img, angle)
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            logger.info("deskewed", angle_deg=round(angle, 2))

        # Adaptive threshold
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10
        )

        # Morphological close to fill small wall gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Remove small connected components (noise)
        binary = self._remove_small_components(binary, min_area=100)

        # Resize if requested
        if target_size:
            w, h = target_size
            color_img = cv2.resize(color_img, (w, h), interpolation=cv2.INTER_AREA)
            gray = cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA)
            binary = cv2.resize(binary, (w, h), interpolation=cv2.INTER_NEAREST)

        logger.info("preprocessed", shape=color_img.shape[:2])
        return {
            "original": color_img,
            "gray": gray,
            "binary": binary,
            "color_clean": color_img.copy(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_image(path: Path) -> np.ndarray:
        """Load image from disk, handling PDF via pdf2image if needed."""
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pdf2image import convert_from_path

                pages = convert_from_path(str(path), dpi=_PDF_DPI, first_page=1, last_page=1)
                pil_img = pages[0].convert("RGB")
                return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except ImportError:
                raise ImportError("pdf2image is required for PDF input. pip install pdf2image")
        else:
            img = cv2.imread(str(path))
            if img is None:
                raise FileNotFoundError(f"Cannot load image: {path}")
            return img

    @staticmethod
    def _detect_skew(gray: np.ndarray) -> float:
        """Detect dominant line angle via HoughLinesP and return correction angle."""
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
        if lines is None:
            return 0.0

        angles: list[float] = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal / near-vertical lines
            if abs(angle) < 15 or abs(angle - 90) < 15 or abs(angle + 90) < 15:
                angles.append(angle)

        if not angles:
            return 0.0

        # Median of near-zero angles
        near_zero = [a for a in angles if abs(a) < 15]
        if near_zero:
            return float(np.median(near_zero))
        return 0.0

    @staticmethod
    def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
        h, w = image.shape[:2]
        center = (w / 2, h / 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))

    @staticmethod
    def _remove_small_components(binary: np.ndarray, min_area: int = 100) -> np.ndarray:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        cleaned = np.zeros_like(binary)
        for i in range(1, num_labels):
            if stats[i, cv2.CC_STAT_AREA] >= min_area:
                cleaned[labels == i] = 255
        return cleaned

    # ------------------------------------------------------------------
    # Stage 1 — VLM-ready payload
    # ------------------------------------------------------------------

    def prepare_for_vlm(
        self,
        image_path: str | Path,
        *,
        max_edge_px: int = _VLM_MAX_EDGE_PX,
        max_bytes: int = _VLM_MAX_BYTES,
    ) -> VlmImagePayload:
        """Produce a VLM-ready PNG payload from an uploaded file.

        Steps:

        1. Load the image (PDF pages render at :data:`_PDF_DPI`).
        2. Normalise orientation from EXIF rotation tags (phones and
           scanners often ship a landscape plan as a portrait-oriented
           JPEG with an EXIF rotation flag).
        3. Resolve DPI from EXIF or PDF metadata, falling back to
           :data:`_VLM_FALLBACK_DPI` with an explicit source tag so the
           caller can record the assumption.
        4. Downscale so the longest edge is at most ``max_edge_px``
           (preserving aspect ratio) — Claude's recommended resolution
           for scene classification.
        5. Re-encode as PNG, re-compressing at a lower quality ceiling
           if the first pass exceeds ``max_bytes``.

        The structural CV pipeline (Stage 3+) uses the full-resolution
        buffer from :meth:`preprocess`; the VLM path deliberately trades
        pixels for round-trip latency.
        """

        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"image not found: {image_path}")

        pil_img, dpi, dpi_source = self._load_pil(image_path)

        # EXIF orientation — PIL's transpose returns a new image; we
        # compare the original size against the transposed size to
        # detect whether the flag actually rotated anything.
        original_size = pil_img.size
        pil_img = ImageOps.exif_transpose(pil_img)
        was_rotated = pil_img.size != original_size

        pil_img = pil_img.convert("RGB")
        original_w, original_h = pil_img.size

        # Downscale preserving aspect ratio.
        longest = max(original_w, original_h)
        was_downscaled = longest > max_edge_px
        if was_downscaled:
            scale = max_edge_px / float(longest)
            new_w = max(1, int(round(original_w * scale)))
            new_h = max(1, int(round(original_h * scale)))
            pil_img = pil_img.resize((new_w, new_h), resample=Image.LANCZOS)

        png_bytes = self._encode_png(pil_img, max_bytes=max_bytes)
        w, h = pil_img.size

        logger.info(
            "vlm_payload_prepared",
            path=str(image_path),
            original_size=(original_w, original_h),
            encoded_size=(w, h),
            dpi=dpi,
            dpi_source=dpi_source,
            bytes=len(png_bytes),
            was_rotated=was_rotated,
            was_downscaled=was_downscaled,
        )
        return VlmImagePayload(
            png_bytes=png_bytes,
            width=w,
            height=h,
            original_width=original_w,
            original_height=original_h,
            dpi=dpi,
            dpi_source=dpi_source,
            was_rotated=was_rotated,
            was_downscaled=was_downscaled,
        )

    @staticmethod
    def _load_pil(path: Path) -> tuple[Image.Image, float, str]:
        """Open *path* as a PIL image, returning (img, dpi, dpi_source)."""

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pdf2image import convert_from_path
            except ImportError as exc:
                raise ImportError(
                    "pdf2image is required for PDF input. pip install pdf2image"
                ) from exc
            pages = convert_from_path(
                str(path), dpi=_PDF_DPI, first_page=1, last_page=1
            )
            return pages[0].convert("RGB"), float(_PDF_DPI), "pdf"

        img = Image.open(path)
        dpi_tuple = img.info.get("dpi")
        if dpi_tuple and isinstance(dpi_tuple, tuple) and dpi_tuple[0]:
            dpi = float(dpi_tuple[0])
            dpi_source = "exif"
        else:
            dpi = _VLM_FALLBACK_DPI
            dpi_source = "fallback"
        return img, dpi, dpi_source

    @staticmethod
    def _encode_png(img: Image.Image, *, max_bytes: int) -> bytes:
        """Encode *img* as PNG, downscaling once more if we blow the cap.

        A 1568-px-longest-edge PNG of a typical floor plan is ~400-800 KB,
        comfortably under Claude's 5 MB ceiling.  The fallback only fires
        on unusually detailed inputs (e.g. high-contrast scans with a
        lot of text); we halve the resolution in that case rather than
        drop to JPEG, since classification accuracy on architectural
        drawings is sensitive to antialiasing artefacts.
        """

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data

        w, h = img.size
        smaller = img.resize(
            (max(1, w // 2), max(1, h // 2)), resample=Image.LANCZOS
        )
        buf2 = io.BytesIO()
        smaller.save(buf2, format="PNG", optimize=True)
        return buf2.getvalue()
