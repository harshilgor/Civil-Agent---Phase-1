"""Fused boundary/wall maps → RoomFormer/PolyRoom-compatible density maps (256×256)."""

from __future__ import annotations

from typing import Any

import numpy as np


def synthesize_density_map(
    fused_boundary: Any,
    fused_wall: Any | None = None,
    size: tuple[int, int] = (256, 256),
) -> Any:
    """Grayscale normalized occupancy for downstream room polygon models."""
    if fused_boundary is None and fused_wall is None:
        raise ValueError("At least one of fused_boundary or fused_wall is required.")

    parts: list[np.ndarray] = []
    if fused_boundary is not None:
        parts.append(np.asarray(fused_boundary, dtype=np.float32))
    if fused_wall is not None:
        parts.append(np.asarray(fused_wall, dtype=np.float32))

    base = np.mean(parts, axis=0)
    base = np.squeeze(base)
    if base.ndim != 2:
        raise ValueError(f"Expected 2D boundary/wall map, got shape={base.shape}")

    base_min = float(base.min())
    base_max = float(base.max())
    if base_max > base_min:
        base = (base - base_min) / (base_max - base_min)
    else:
        base = np.zeros_like(base, dtype=np.float32)

    # Keep OpenCV optional to avoid hard requirement in constrained environments.
    try:
        import cv2  # type: ignore

        resized = cv2.resize(base, size, interpolation=cv2.INTER_AREA)
    except Exception:
        pil_image = np.clip(base * 255.0, 0, 255).astype(np.uint8)
        from PIL import Image

        resized = np.asarray(
            Image.fromarray(pil_image, mode="L").resize(size, Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        resized /= 255.0

    return np.clip(resized, 0.0, 1.0).astype(np.float32)
