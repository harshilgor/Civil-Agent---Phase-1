"""PNG/JPG/PDF rasterization and format detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_raster_input(path: str | Path) -> tuple[Any, str]:
    """
    Load a floor plan raster. Returns (array RGB uint8 or float, format_hint).
    PDF support requires optional dependencies (e.g. pdf2image).
    """
    _ = Path(path).resolve()
    raise NotImplementedError("Wire to Pillow/OpenCV and optional PDF rasterization.")
