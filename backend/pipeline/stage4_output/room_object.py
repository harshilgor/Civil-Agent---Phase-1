"""Room polygon, area, label, confidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RoomObject:
    polygon: Any
    area_m2: float | None = None
    label: str = "unknown"
    confidence: float = 0.0
