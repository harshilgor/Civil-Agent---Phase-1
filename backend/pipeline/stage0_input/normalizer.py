"""Resize, CLAHE, grayscale+RGB, deskew."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

def normalize_image(image: Any, target_max_dim: int = 1024) -> Any:
    """Resize, optional CLAHE, ensure 3-channel for downstream models."""
    arr = np.asarray(image)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if arr.ndim != 3:
        raise ValueError(f"Expected HxWxC input, got shape={arr.shape}")
    if arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.shape[2] > 3:
        arr = arr[..., :3]

    if arr.dtype != np.uint8:
        arr = arr.astype(np.float32)
        if arr.max() <= 1.0:
            arr *= 255.0
        arr = np.clip(arr, 0.0, 255.0).astype(np.uint8)

    h, w = arr.shape[:2]
    scale = 1.0
    longest = max(h, w)
    if longest > target_max_dim and target_max_dim > 0:
        scale = target_max_dim / float(longest)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        arr = np.asarray(
            Image.fromarray(arr, mode="RGB").resize((new_w, new_h), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )

    # Lightweight contrast normalization fallback (CLAHE if cv2 is available).
    try:
        import cv2

        lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        merged = cv2.merge((cl, a, b))
        arr = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    except Exception:
        pass

    return arr
