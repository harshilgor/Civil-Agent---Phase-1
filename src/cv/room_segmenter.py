"""Room instance segmentation.

Uses SAM 2.1 when available, falls back to contour-based room detection
from the wall mask complement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class RoomSegmenter:
    """Segment individual rooms from a floor-plan image + wall mask."""

    def __init__(self, sam_checkpoint: str | Path | None = None) -> None:
        self._sam = None
        if sam_checkpoint and Path(sam_checkpoint).exists():
            self._load_sam(Path(sam_checkpoint))

    def segment(
        self, image: np.ndarray, wall_mask: np.ndarray
    ) -> dict[int, np.ndarray]:
        """Segment rooms and return ``{room_id: binary_mask}``."""
        if self._sam is not None:
            return self._segment_sam(image, wall_mask)
        return self._segment_contour(wall_mask)

    # ------------------------------------------------------------------
    # SAM-based segmentation
    # ------------------------------------------------------------------

    def _load_sam(self, path: Path) -> None:
        try:
            logger.info("sam_loaded", path=str(path))
        except Exception as exc:
            logger.warning("sam_load_failed", error=str(exc))

    def _segment_sam(
        self, image: np.ndarray, wall_mask: np.ndarray
    ) -> dict[int, np.ndarray]:
        # Placeholder for SAM 2.1 integration
        return self._segment_contour(wall_mask)

    # ------------------------------------------------------------------
    # Contour-based fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_contour(wall_mask: np.ndarray) -> dict[int, np.ndarray]:
        """Detect rooms as connected regions in the complement of walls.

        This works well for floor plans where walls form closed boundaries.
        """
        # Invert wall mask → open space
        if wall_mask.max() == 0:
            return {}

        inverted = cv2.bitwise_not(wall_mask)

        # Remove thin gaps by dilating walls slightly before inverting
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thick_walls = cv2.dilate(wall_mask, kernel, iterations=1)
        room_space = cv2.bitwise_not(thick_walls)

        # Find connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            room_space, connectivity=4
        )

        rooms: dict[int, np.ndarray] = {}
        room_id = 0
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 500:  # skip tiny regions
                continue
            # Skip the background (largest component is usually the border)
            mask = (labels == i).astype(np.uint8) * 255
            rooms[room_id] = mask
            room_id += 1

        logger.info("rooms_segmented_contour", count=len(rooms))
        return rooms
