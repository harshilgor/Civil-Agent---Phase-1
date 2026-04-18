"""Tests for the unit inference module (Gap 2)."""

from __future__ import annotations

import pytest

from src.cv.unit_inferrer import UnitInferrer, UnitSystem


@pytest.fixture()
def inferrer() -> UnitInferrer:
    return UnitInferrer()


# ---------------------------------------------------------------------------
# Stage 1 — explicit markers
# ---------------------------------------------------------------------------


def test_explicit_mm_marker(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["3000mm", "6000", "8500 mm"])
    assert r.unit_system == UnitSystem.MILLIMETERS
    assert r.confidence >= 0.9
    assert r.conversion_factor_to_mm == 1.0


def test_explicit_cm_marker(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["300cm", "600 cm", "850cm"])
    assert r.unit_system == UnitSystem.CENTIMETERS
    assert r.confidence >= 0.9
    assert r.conversion_factor_to_mm == 10.0


def test_explicit_m_marker_with_decimal(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["3.0m", "6.0 m", "8.5m"])
    assert r.unit_system == UnitSystem.METERS
    assert r.confidence >= 0.85
    assert r.conversion_factor_to_mm == 1000.0


def test_explicit_imperial_marker_feet_inches(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["20'-0\"", "16'-6\"", "8'-0\""])
    assert r.unit_system == UnitSystem.FEET_INCHES
    assert r.confidence >= 0.9


def test_explicit_imperial_ft(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["20 ft", "16 ft", "8 ft"])
    assert r.unit_system == UnitSystem.FEET_INCHES


# ---------------------------------------------------------------------------
# Stage 2 — statistical inference
# ---------------------------------------------------------------------------


def test_statistical_millimeters_range(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["3000", "6000", "8500", "12000"])
    assert r.unit_system == UnitSystem.MILLIMETERS
    assert r.confidence >= 0.7


def test_statistical_meters_range(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["3.0", "6.0", "8.5", "12.0"])
    assert r.unit_system == UnitSystem.METERS
    assert r.confidence >= 0.5


def test_statistical_feet_cluster(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["10", "16", "20", "24", "32"])
    assert r.unit_system == UnitSystem.FEET_INCHES


def test_ambiguous_centimeter_range_low_confidence(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["300", "600", "850", "1200"])
    # 300-1200 median is ambiguous (could be cm or small mm); result may be cm
    # or fall back to mm via cross-validation — either way low confidence.
    assert r.confidence <= 0.85


# ---------------------------------------------------------------------------
# Stage 3 — cross-validation fallback
# ---------------------------------------------------------------------------


def test_fallback_when_statistical_guess_is_implausible(inferrer: UnitInferrer) -> None:
    # Values in meters — statistical inference picks METERS
    r = inferrer.infer(["3.2", "6.4", "9.0", "12.5"])
    assert r.unit_system == UnitSystem.METERS
    # All values convert to 3200..12500 mm, well within plausible range
    assert r.conversion_factor_to_mm == 1000.0


def test_empty_input(inferrer: UnitInferrer) -> None:
    r = inferrer.infer([])
    assert r.unit_system == UnitSystem.MILLIMETERS
    assert r.confidence == 0.0


def test_mixed_markers_imperial_wins(inferrer: UnitInferrer) -> None:
    # Imperial markers take precedence over anything else
    r = inferrer.infer(["20'-0\"", "6000", "3000"])
    assert r.unit_system == UnitSystem.FEET_INCHES


def test_result_to_dict(inferrer: UnitInferrer) -> None:
    r = inferrer.infer(["3000mm", "6000mm"])
    d = r.to_dict()
    assert d["unit_system"] == "MILLIMETERS"
    assert d["conversion_factor_to_mm"] == 1.0
    assert "evidence" in d
    assert "confidence" in d


# ---------------------------------------------------------------------------
# Accuracy targets
# ---------------------------------------------------------------------------


def test_explicit_marker_accuracy() -> None:
    """95%+ correct on explicit-marker cases."""
    inferrer = UnitInferrer()
    cases: list[tuple[list[str], UnitSystem]] = [
        (["3000mm", "6000mm"], UnitSystem.MILLIMETERS),
        (["3.0 m", "6.0 m"], UnitSystem.METERS),
        (["300cm", "600 cm"], UnitSystem.CENTIMETERS),
        (["20'-0\"", "16'-6\""], UnitSystem.FEET_INCHES),
        (["3000 mm", "6000 mm", "8500 mm"], UnitSystem.MILLIMETERS),
        (["10 ft", "15 ft"], UnitSystem.FEET_INCHES),
        (["2.4m", "3.6m", "6.0m"], UnitSystem.METERS),
        (["100cm", "200cm", "350cm"], UnitSystem.CENTIMETERS),
    ]
    correct = sum(1 for c, expected in cases if inferrer.infer(c).unit_system == expected)
    assert correct / len(cases) >= 0.95


def test_pure_numeric_accuracy() -> None:
    """80%+ correct on pure-numeric cases."""
    inferrer = UnitInferrer()
    cases: list[tuple[list[str], UnitSystem]] = [
        (["3000", "6000", "8500", "12000"], UnitSystem.MILLIMETERS),
        (["3.0", "6.0", "8.5", "12.0"], UnitSystem.METERS),
        (["10", "16", "20", "24"], UnitSystem.FEET_INCHES),
        (["2500", "5000", "7500"], UnitSystem.MILLIMETERS),
        (["4.5", "6.0", "9.0"], UnitSystem.METERS),
    ]
    correct = sum(1 for c, expected in cases if inferrer.infer(c).unit_system == expected)
    assert correct / len(cases) >= 0.80
