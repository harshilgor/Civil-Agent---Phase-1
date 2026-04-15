"""OCR + heuristic line detection for printed dimensions."""

from __future__ import annotations

from typing import Any


def detect_dimensions(image: Any) -> list[dict[str, Any]]:
    raise NotImplementedError("OCR + line-aligned dimension candidates.")
