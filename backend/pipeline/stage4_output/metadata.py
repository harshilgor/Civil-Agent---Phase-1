"""Agreement metrics, boundary strength, uncertainty flags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutputMetadata:
    agreement: dict[str, float] = field(default_factory=dict)
    boundary_strength: float = 0.0
    uncertainty_flags: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
