"""Fused boundary/wall maps → RoomFormer/PolyRoom-compatible density maps (256×256)."""

from __future__ import annotations

from typing import Any


def synthesize_density_map(
    fused_boundary: Any,
    fused_wall: Any | None = None,
    size: tuple[int, int] = (256, 256),
) -> Any:
    """Grayscale normalized occupancy for downstream room polygon models."""
    raise NotImplementedError("Fuse boundary logits/masks and resize/normalize to 256×256.")
