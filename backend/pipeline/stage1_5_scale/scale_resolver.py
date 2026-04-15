"""Cross-validate OCR, scale bar, title block; apply fallback hierarchy."""

from __future__ import annotations

from typing import Any


def resolve_scale(
    image: Any,
    ocr_candidates: list[dict[str, Any]] | None = None,
    scale_bar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns meters_per_pixel or equivalent and confidence."""
    raise NotImplementedError("Merge dimension_detector + scale_bar_detector outputs.")
