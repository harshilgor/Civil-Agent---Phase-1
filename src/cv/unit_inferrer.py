"""Unit-system inference for OCR-extracted dimension text.

Given a list of raw dimension strings from a single floor plan, the inferrer
returns the most likely unit system and a conversion factor to millimeters.

Deterministic two-stage algorithm:

1. Look for *explicit* unit markers (``mm``, ``cm``, ``m``, ``ft``, ``in``,
   ``'``, ``"``). Any explicit marker wins.
2. If no markers, apply *statistical* inference on the numeric magnitudes —
   typical building dimensions cluster in known ranges per unit.
3. Validate the chosen unit by converting to millimeters and checking that
   most values fall within plausible wall / room ranges. If not, fall back
   to the next most likely unit.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class UnitSystem(str, Enum):
    MILLIMETERS = "MILLIMETERS"
    CENTIMETERS = "CENTIMETERS"
    METERS = "METERS"
    FEET_INCHES = "FEET_INCHES"


# Conversion factors to mm
_FACTORS: dict[UnitSystem, float] = {
    UnitSystem.MILLIMETERS: 1.0,
    UnitSystem.CENTIMETERS: 10.0,
    UnitSystem.METERS: 1000.0,
    UnitSystem.FEET_INCHES: 304.8,  # nominal per-foot; imperial strings handled specially
}


# Plausible range of building dimensions in mm
PLAUSIBLE_WALL_MIN_MM = 100.0
PLAUSIBLE_WALL_MAX_MM = 50_000.0
PLAUSIBLE_ROOM_MIN_MM = 1_500.0
PLAUSIBLE_ROOM_MAX_MM = 30_000.0
OUT_OF_RANGE_FRACTION_LIMIT = 0.30


@dataclass
class UnitInferenceResult:
    unit_system: UnitSystem
    conversion_factor_to_mm: float
    confidence: float
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_system": self.unit_system.value,
            "conversion_factor_to_mm": self.conversion_factor_to_mm,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_MM_MARKER = re.compile(r"(?<![a-zA-Z])mm\b", re.IGNORECASE)
_CM_MARKER = re.compile(r"(?<![a-zA-Z])cm\b", re.IGNORECASE)
_M_MARKER = re.compile(r"(?<![a-zA-Z])m\b", re.IGNORECASE)  # catches "m" but not "mm"/"cm"
_IMPERIAL_MARKER = re.compile(r"(\d'\s*\d*\"?|ft\b|\sin\b|[\u2032\u2033])", re.IGNORECASE)


class UnitInferrer:
    """Infer the unit system used on a floor plan from extracted dimensions."""

    def infer(self, dimension_strings: list[str]) -> UnitInferenceResult:
        """Return the best-guess ``UnitInferenceResult`` for ``dimension_strings``."""
        if not dimension_strings:
            return UnitInferenceResult(
                unit_system=UnitSystem.MILLIMETERS,
                conversion_factor_to_mm=1.0,
                confidence=0.0,
                evidence="no dimension strings provided — defaulting to MILLIMETERS",
            )

        # Stage 1 — explicit markers
        marker_result = self._detect_explicit_markers(dimension_strings)
        if marker_result is not None:
            # Cross-validate even the "definitive" answer
            numeric_values = _extract_numeric(dimension_strings)
            validated = self._cross_validate(marker_result, numeric_values)
            if validated is not None:
                logger.info("unit_inferred", **validated.to_dict())
                return validated
            logger.info("unit_inferred", **marker_result.to_dict())
            return marker_result

        # Stage 2 — statistical inference
        numeric_values = _extract_numeric(dimension_strings)
        statistical = self._statistical_inference(numeric_values)

        # Stage 3 — cross-validate and fall back if needed
        validated = self._cross_validate(statistical, numeric_values) or statistical
        logger.info("unit_inferred", **validated.to_dict())
        return validated

    # ------------------------------------------------------------------
    # Stage 1 — explicit markers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_explicit_markers(strings: list[str]) -> UnitInferenceResult | None:
        has_imperial = any(_IMPERIAL_MARKER.search(s) for s in strings)
        has_mm = any(_MM_MARKER.search(s) for s in strings)
        has_cm = any(_CM_MARKER.search(s) for s in strings)
        # For "m" we must exclude strings where "mm" or "cm" already matched
        def _has_bare_m(s: str) -> bool:
            if _MM_MARKER.search(s) or _CM_MARKER.search(s):
                return False
            # "m" must appear AND numeric part should have a decimal
            if not _M_MARKER.search(s):
                return False
            # Require a decimal in the numeric portion to discriminate from partial matches
            return bool(re.search(r"\d+\.\d+", s))

        has_m = any(_has_bare_m(s) for s in strings)

        if has_imperial:
            return UnitInferenceResult(
                unit_system=UnitSystem.FEET_INCHES,
                conversion_factor_to_mm=_FACTORS[UnitSystem.FEET_INCHES],
                confidence=0.95,
                evidence="explicit imperial marker found (feet/inches)",
            )
        if has_mm:
            return UnitInferenceResult(
                unit_system=UnitSystem.MILLIMETERS,
                conversion_factor_to_mm=1.0,
                confidence=0.98,
                evidence="explicit mm marker found",
            )
        if has_cm:
            return UnitInferenceResult(
                unit_system=UnitSystem.CENTIMETERS,
                conversion_factor_to_mm=10.0,
                confidence=0.95,
                evidence="explicit cm marker found",
            )
        if has_m:
            return UnitInferenceResult(
                unit_system=UnitSystem.METERS,
                conversion_factor_to_mm=1000.0,
                confidence=0.92,
                evidence="explicit m marker with decimal found",
            )
        return None

    # ------------------------------------------------------------------
    # Stage 2 — statistical inference
    # ------------------------------------------------------------------

    @staticmethod
    def _statistical_inference(values: list[float]) -> UnitInferenceResult:
        if not values:
            return UnitInferenceResult(
                unit_system=UnitSystem.MILLIMETERS,
                conversion_factor_to_mm=1.0,
                confidence=0.0,
                evidence="no numeric values extracted",
            )
        median = statistics.median(values)

        if 1000 <= median <= 50_000:
            return UnitInferenceResult(
                unit_system=UnitSystem.MILLIMETERS,
                conversion_factor_to_mm=1.0,
                confidence=0.75,
                evidence=f"median value {median:.0f} suggests millimeters",
            )
        if 1 <= median <= 50:
            if 5 <= median <= 40:
                # Cluster check — if values are tightly clustered 5-40, likely feet
                in_feet_band = sum(1 for v in values if 5 <= v <= 40)
                if in_feet_band / len(values) > 0.80:
                    return UnitInferenceResult(
                        unit_system=UnitSystem.FEET_INCHES,
                        conversion_factor_to_mm=304.8,
                        confidence=0.60,
                        evidence=(
                            f"median {median:.1f} and >80% of values in 5-40 range — "
                            f"likely imperial (feet) without explicit markers"
                        ),
                    )
            return UnitInferenceResult(
                unit_system=UnitSystem.METERS,
                conversion_factor_to_mm=1000.0,
                confidence=0.70,
                evidence=f"median value {median:.1f} suggests meters",
            )
        if 100 <= median <= 5000:
            return UnitInferenceResult(
                unit_system=UnitSystem.CENTIMETERS,
                conversion_factor_to_mm=10.0,
                confidence=0.40,
                evidence=(
                    f"median {median:.0f} is ambiguous — could be cm or small mm; "
                    "choosing cm with low confidence"
                ),
            )
        return UnitInferenceResult(
            unit_system=UnitSystem.MILLIMETERS,
            conversion_factor_to_mm=1.0,
            confidence=0.30,
            evidence=f"median {median:.0f} fits no standard range — defaulting to mm",
        )

    # ------------------------------------------------------------------
    # Stage 3 — cross-validation
    # ------------------------------------------------------------------

    def _cross_validate(
        self,
        guess: UnitInferenceResult,
        values: list[float],
    ) -> UnitInferenceResult | None:
        """Check that the chosen unit yields plausible mm values. If not,
        iterate through alternatives in descending plausibility order.
        """
        if not values:
            return guess

        def _frac_in_range(mm_vals: list[float]) -> float:
            in_range = sum(1 for v in mm_vals if PLAUSIBLE_WALL_MIN_MM <= v <= PLAUSIBLE_WALL_MAX_MM)
            return in_range / len(mm_vals)

        candidates = [guess.unit_system] + [
            u for u in (
                UnitSystem.MILLIMETERS,
                UnitSystem.METERS,
                UnitSystem.CENTIMETERS,
                UnitSystem.FEET_INCHES,
            ) if u != guess.unit_system
        ]

        best: UnitInferenceResult | None = None
        best_frac = -1.0
        for u in candidates:
            factor = _FACTORS[u]
            mm_vals = [v * factor for v in values]
            frac = _frac_in_range(mm_vals)
            if frac >= 1 - OUT_OF_RANGE_FRACTION_LIMIT:
                if u == guess.unit_system:
                    return guess  # first-guess validated
                return UnitInferenceResult(
                    unit_system=u,
                    conversion_factor_to_mm=factor,
                    confidence=max(0.30, guess.confidence - 0.30),
                    evidence=(
                        f"initial guess {guess.unit_system.value} rejected "
                        f"({_frac_in_range([v * _FACTORS[guess.unit_system] for v in values]):.0%} in range); "
                        f"fallback to {u.value} with {frac:.0%} in plausible range"
                    ),
                )
            if frac > best_frac:
                best_frac = frac
                best = UnitInferenceResult(
                    unit_system=u,
                    conversion_factor_to_mm=factor,
                    confidence=max(0.20, guess.confidence - 0.40),
                    evidence=(
                        f"no unit yielded fully plausible values; best fit "
                        f"{u.value} with {frac:.0%} in plausible range"
                    ),
                )
        return best


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_NUM_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


def _extract_numeric(strings: list[str]) -> list[float]:
    """Pull the leading numeric magnitude out of each string (ignoring units)."""
    out: list[float] = []
    for s in strings:
        # Handle imperial "20'-0\"" first
        m = re.match(r"(\d+)['\u2019]-?(\d+)?[\"\u2033]?", s.strip())
        if m:
            feet = float(m.group(1))
            inches = float(m.group(2) or 0)
            out.append(feet + inches / 12.0)  # in feet units for downstream stats
            continue
        nums = _NUM_PATTERN.findall(s.replace(",", ""))
        if nums:
            try:
                out.append(float(nums[0]))
            except ValueError:
                pass
    return out


__all__ = [
    "PLAUSIBLE_ROOM_MAX_MM",
    "PLAUSIBLE_ROOM_MIN_MM",
    "PLAUSIBLE_WALL_MAX_MM",
    "PLAUSIBLE_WALL_MIN_MM",
    "UnitInferenceResult",
    "UnitInferrer",
    "UnitSystem",
]
