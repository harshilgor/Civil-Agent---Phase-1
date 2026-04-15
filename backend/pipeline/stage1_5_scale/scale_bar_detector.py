"""Scale bar and title block parsing."""

from __future__ import annotations

from typing import Any


def detect_scale_bar(image: Any) -> dict[str, Any] | None:
    raise NotImplementedError("Locate scale bar segments and read ratio.")
