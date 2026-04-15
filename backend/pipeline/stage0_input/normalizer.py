"""Resize, CLAHE, grayscale+RGB, deskew."""

from __future__ import annotations

from typing import Any


def normalize_image(image: Any, target_max_dim: int = 1024) -> Any:
    """Resize, optional CLAHE, ensure 3-channel for downstream models."""
    raise NotImplementedError("Implement resize, CLAHE, deskew per pipeline.yaml.")
