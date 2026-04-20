"""Overall confidence scoring for Phase 3.

The score starts at ``1.0`` and subtracts penalties for low-confidence
assumptions, incomplete upstream data, warnings, and missing site-specific
hazard inputs. The final value is clamped to ``[0.10, 1.00]``.
"""

from __future__ import annotations

from typing import Any

from .models.enums import ConfidenceLevel, WarningLevel
from .models.outputs import AssumptionRegister, Phase3Warning


def compute_overall_confidence(
    building_graph: dict[str, Any],
    structural_design_graph: dict[str, Any],
    assumption_register: AssumptionRegister,
    warnings: list[Phase3Warning],
) -> float:
    """Return an overall numeric confidence in the Phase 3 output."""

    base = 1.0

    low_conf_penalty = min(0.30, 0.05 * assumption_register.low_confidence_count)
    base -= low_conf_penalty

    overall_bg = (
        building_graph.get("metadata", {})
        .get("confidence_scores", {})
        .get("overall")
    )
    if overall_bg is not None and float(overall_bg) < 0.7:
        base -= 0.15

    sg_confidence = (
        structural_design_graph.get("metadata", {}).get("confidence_overall")
    )
    if sg_confidence is not None and float(sg_confidence) < 0.7:
        base -= 0.10

    error_warnings = sum(1 for w in warnings if w.level == WarningLevel.ERROR)
    warn_warnings = sum(1 for w in warnings if w.level == WarningLevel.WARNING)
    base -= 0.20 * error_warnings
    base -= min(0.15, 0.05 * warn_warnings)

    Ss_rec = assumption_register.get_by_id("seismic_Ss")
    S1_rec = assumption_register.get_by_id("seismic_S1")
    if Ss_rec is not None and Ss_rec.confidence < 0.6:
        base -= 0.10
    if S1_rec is not None and S1_rec.confidence < 0.6:
        base -= 0.10

    wind_rec = assumption_register.get_by_id("basic_wind_speed")
    if wind_rec is not None and wind_rec.confidence < 0.6:
        base -= 0.05

    regularity = structural_design_graph.get("metadata", {}).get("building_regularity")
    if regularity == "irregular":
        base -= 0.10

    return max(0.10, min(1.0, base))


def confidence_level(score: float) -> ConfidenceLevel:
    """Map a numeric confidence to the qualitative bucket."""

    if score > 0.85:
        return ConfidenceLevel.HIGH
    if score >= 0.60:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW
