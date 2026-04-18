"""Floor-plan image preprocessing.

Handles PDF→image conversion, deskewing, adaptive thresholding,
morphological cleanup, and noise removal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

# PDF rendering DPI
_PDF_DPI = 300


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
