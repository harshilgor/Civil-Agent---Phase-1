"""PNG/JPG/PDF rasterization and format detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_raster_input(path: str | Path) -> tuple[Any, str]:
    """
    Load a floor plan raster. Returns (array RGB uint8 or float, format_hint).
    PDF support requires optional dependencies (e.g. pdf2image).
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # pymupdf
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("PDF input requires pymupdf (`pip install pymupdf`).") from exc

        doc = fitz.open(str(p))
        if len(doc) == 0:
            raise ValueError(f"PDF has no pages: {p}")
        page = doc[0]
        pix = page.get_pixmap(dpi=150, alpha=False)
        data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            data = data[..., :3]
        return data, "pdf"

    img = Image.open(p).convert("RGB")
    arr = np.asarray(img, dtype=np.uint8)
    fmt = suffix.lstrip(".") if suffix else "image"
    return arr, fmt
