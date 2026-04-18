"""Input validation helpers used across modules."""

from __future__ import annotations

from typing import Sequence


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValidationError(name, f"must be positive, got {value}")


def validate_range(value: float, lo: float, hi: float, name: str) -> None:
    if not (lo <= value <= hi):
        raise ValidationError(name, f"must be in [{lo}, {hi}], got {value}")


def validate_non_empty(seq: Sequence, name: str) -> None:
    if not seq:
        raise ValidationError(name, "must not be empty")


def validate_ascending(values: Sequence[float], name: str) -> None:
    for i in range(1, len(values)):
        if values[i] <= values[i - 1]:
            raise ValidationError(
                name,
                f"must be strictly ascending; index {i - 1} ({values[i - 1]}) "
                f">= index {i} ({values[i]})",
            )


def validate_closed_polygon(pts: list[list[float]], name: str) -> None:
    if len(pts) < 3:
        raise ValidationError(name, "polygon must have at least 3 points")
    for i, pt in enumerate(pts):
        if len(pt) != 2:
            raise ValidationError(name, f"point {i} must be [x, y], got {pt}")
