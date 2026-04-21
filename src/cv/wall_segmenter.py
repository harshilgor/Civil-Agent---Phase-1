"""U-Net wall / element segmentation.

Uses a ResNet-152 encoder U-Net from ``segmentation_models_pytorch``,
trained on CubiCasa5K.  When no weights are available, falls back to
a simple threshold-based wall detector.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Class indices for the 17-class segmentation
CLASS_NAMES = [
    "background", "wall", "door", "window", "stair",
    "kitchen", "bedroom", "bathroom", "living_room", "corridor",
    "lobby", "office", "conference", "storage", "mechanical",
    "elevator", "stairwell",
]
WALL_CLASS_IDX = 1


class WallSegmenter:
    """Segment wall pixels from a floor-plan image.

    If a trained model checkpoint is provided, uses U-Net inference.
    Otherwise falls back to classical thresholding.
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model = None
        self._device = "cpu"
        if model_path and Path(model_path).exists():
            self._load_model(Path(model_path))

    def segment(self, image: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Segment *image* (BGR or binary) into wall mask + element masks.

        Returns:
            ``(wall_mask, element_masks)`` where wall_mask is a binary uint8
            image and element_masks maps class names to binary masks.
        """
        if self._model is not None:
            return self._segment_unet(image)
        return self._segment_classical(image)

    # ------------------------------------------------------------------
    # U-Net inference (requires trained weights)
    # ------------------------------------------------------------------

    def _load_model(self, path: Path) -> None:
        try:
            import torch
            import segmentation_models_pytorch as smp

            self._model = smp.Unet(
                encoder_name="resnet152",
                encoder_weights=None,
                in_channels=3,
                classes=len(CLASS_NAMES),
            )
            state = torch.load(str(path), map_location="cpu")
            self._model.load_state_dict(state)
            self._model.eval()

            if torch.cuda.is_available():
                self._device = "cuda"
                self._model = self._model.cuda()

            logger.info("wall_segmenter_loaded", path=str(path), device=self._device)
        except Exception as exc:
            logger.warning("wall_segmenter_load_failed", error=str(exc))
            self._model = None

    def _segment_unet(self, image: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        import torch

        # Preprocess
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        h, w = img_rgb.shape[:2]
        resized = cv2.resize(img_rgb, (512, 512))
        tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0).float() / 255.0

        if self._device == "cuda":
            tensor = tensor.cuda()

        with torch.no_grad():
            logits = self._model(tensor)
            pred = torch.argmax(logits, dim=1).squeeze().cpu().numpy()

        # Resize predictions back
        pred_full = cv2.resize(pred.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)

        wall_mask = (pred_full == WALL_CLASS_IDX).astype(np.uint8) * 255
        element_masks = {}
        for idx, name in enumerate(CLASS_NAMES):
            if idx == 0:
                continue
            mask = (pred_full == idx).astype(np.uint8) * 255
            if mask.any():
                element_masks[name] = mask

        return wall_mask, element_masks

    # ------------------------------------------------------------------
    # Classical fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_classical(image: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Simple morphological wall extraction for when no model is available."""
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Otsu threshold
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Morphological operations to isolate walls (thick dark lines)
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        horiz = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
        vert = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_v)
        wall_mask = cv2.bitwise_or(horiz, vert)

        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        wall_mask = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        return wall_mask, {"wall": wall_mask}
