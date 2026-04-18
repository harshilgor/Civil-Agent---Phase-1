"""Unit conversion helpers.

The canonical internal unit is **millimeters (mm)**.
"""

from __future__ import annotations

# Conversion factors → mm
_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1_000.0,
    "in": 25.4,
    "ft": 304.8,
    "yd": 914.4,
}

# DXF $INSUNITS codes → unit string
DXF_INSUNITS: dict[int, str] = {
    1: "in",
    2: "ft",
    4: "mm",
    5: "cm",
    6: "m",
}


def to_mm(value: float, unit: str) -> float:
    """Convert *value* in *unit* to millimeters."""
    unit = unit.lower().strip()
    factor = _TO_MM.get(unit)
    if factor is None:
        raise ValueError(f"Unknown unit '{unit}'. Supported: {list(_TO_MM)}")
    return value * factor


def from_mm(value_mm: float, unit: str) -> float:
    """Convert *value_mm* from millimeters to *unit*."""
    unit = unit.lower().strip()
    factor = _TO_MM.get(unit)
    if factor is None:
        raise ValueError(f"Unknown unit '{unit}'. Supported: {list(_TO_MM)}")
    return value_mm / factor


def mm_to_m2(area_mm2: float) -> float:
    """Convert mm² to m²."""
    return area_mm2 / 1_000_000


def m2_to_mm2(area_m2: float) -> float:
    """Convert m² to mm²."""
    return area_m2 * 1_000_000
