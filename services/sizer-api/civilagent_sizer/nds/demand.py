"""Beam demand formulas for simple and equal-span continuous beams."""

from dataclasses import dataclass

from civilagent_sizer.nds.checks import (
    simple_uniform_deflection,
    simple_uniform_moment,
    simple_uniform_shear,
)

SIMPLE_SPAN_SOURCE = (
    "Classical beam mechanics; AISC Steel Construction Manual Table 3-23 Case 1 "
    "and NDS commentary references"
)
TWO_SPAN_SOURCE = (
    "Roark's Formulas for Stress and Strain, 8th edition, Table 8.1; "
    "AISC Steel Manual Table 3-23 Case 3"
)
THREE_SPAN_SOURCE = (
    "Roark's Formulas for Stress and Strain, 8th edition, Table 8.1 Case 5; "
    "AISC Steel Manual Table 3-23 Case 5"
)

# Two-span continuous beam, equal spans, uniform load
# Maximum positive deflection in end span
# Coefficient: 1/185 = 0.005405405...
# Source: Roark's Formulas for Stress and Strain, 8th edition, Table 8.1, Case 3
DELTA_COEFF_TWO_SPAN = 1.0 / 185.0

# Three-span continuous beam, equal spans, uniform load
# Maximum positive deflection in end span
# Coefficient: 1/145 = 0.006896551...
# Source: Roark's Formulas for Stress and Strain, 8th edition, Table 8.1, Case 5
DELTA_COEFF_THREE_SPAN = 1.0 / 145.0


@dataclass(frozen=True)
class BeamDemand:
    """Demand envelope for one beam span configuration."""

    span_config: str
    span_count: int
    moment_inlb: float
    shear_lb: float
    live_deflection_in: float
    total_deflection_in: float
    end_reactions_lb: tuple[float, ...]
    interior_reactions_lb: tuple[float, ...]
    design_moment_type: str
    source: str
    positive_moment_inlb: float
    negative_moment_inlb: float


def uniform_beam_demand(
    *,
    span_config: str,
    dead_plf: float,
    live_plf: float,
    span_ft: float,
    e_psi: float,
    ix_in4: float,
) -> BeamDemand:
    """Return uniform-load beam demand per cited simple/continuous beam tables."""

    if span_config == "simple":
        return _simple_beam_demand(dead_plf, live_plf, span_ft, e_psi, ix_in4)
    if span_config == "two_span_equal":
        return _two_span_equal_demand(dead_plf, live_plf, span_ft, e_psi, ix_in4)
    if span_config == "three_span_equal":
        return _three_span_equal_demand(dead_plf, live_plf, span_ft, e_psi, ix_in4)
    raise ValueError(f"Unsupported span_config {span_config!r}")


def _simple_beam_demand(
    dead_plf: float,
    live_plf: float,
    span_ft: float,
    e_psi: float,
    ix_in4: float,
) -> BeamDemand:
    total_plf = dead_plf + live_plf
    reaction = simple_uniform_shear(total_plf, span_ft)
    moment = simple_uniform_moment(total_plf, span_ft)
    return BeamDemand(
        span_config="simple",
        span_count=1,
        moment_inlb=moment,
        shear_lb=reaction,
        live_deflection_in=simple_uniform_deflection(live_plf, span_ft, e_psi, ix_in4),
        total_deflection_in=simple_uniform_deflection(total_plf, span_ft, e_psi, ix_in4),
        end_reactions_lb=(reaction, reaction),
        interior_reactions_lb=(),
        design_moment_type="positive",
        source=SIMPLE_SPAN_SOURCE,
        positive_moment_inlb=moment,
        negative_moment_inlb=0.0,
    )


def _two_span_equal_demand(
    dead_plf: float,
    live_plf: float,
    span_ft: float,
    e_psi: float,
    ix_in4: float,
) -> BeamDemand:
    total_plf = dead_plf + live_plf
    moment_positive = (9.0 / 128.0) * total_plf * span_ft**2 * 12.0
    moment_negative = (1.0 / 8.0) * total_plf * span_ft**2 * 12.0
    live_deflection = _coefficient_deflection(
        live_plf, span_ft, e_psi, ix_in4, DELTA_COEFF_TWO_SPAN
    )
    total_deflection = _coefficient_deflection(
        total_plf, span_ft, e_psi, ix_in4, DELTA_COEFF_TWO_SPAN
    )
    return BeamDemand(
        span_config="two_span_equal",
        span_count=2,
        moment_inlb=max(moment_positive, moment_negative),
        shear_lb=(5.0 / 8.0) * total_plf * span_ft,
        live_deflection_in=live_deflection,
        total_deflection_in=total_deflection,
        end_reactions_lb=((3.0 / 8.0) * total_plf * span_ft, (3.0 / 8.0) * total_plf * span_ft),
        interior_reactions_lb=((10.0 / 8.0) * total_plf * span_ft,),
        design_moment_type="negative" if moment_negative >= moment_positive else "positive",
        source=TWO_SPAN_SOURCE,
        positive_moment_inlb=moment_positive,
        negative_moment_inlb=moment_negative,
    )


def _three_span_equal_demand(
    dead_plf: float,
    live_plf: float,
    span_ft: float,
    e_psi: float,
    ix_in4: float,
) -> BeamDemand:
    total_plf = dead_plf + live_plf
    moment_positive = 0.08 * total_plf * span_ft**2 * 12.0
    moment_negative = 0.10 * total_plf * span_ft**2 * 12.0
    live_deflection = _coefficient_deflection(
        live_plf, span_ft, e_psi, ix_in4, DELTA_COEFF_THREE_SPAN
    )
    total_deflection = _coefficient_deflection(
        total_plf, span_ft, e_psi, ix_in4, DELTA_COEFF_THREE_SPAN
    )
    return BeamDemand(
        span_config="three_span_equal",
        span_count=3,
        moment_inlb=max(moment_positive, moment_negative),
        shear_lb=0.6 * total_plf * span_ft,
        live_deflection_in=live_deflection,
        total_deflection_in=total_deflection,
        end_reactions_lb=(0.4 * total_plf * span_ft, 0.4 * total_plf * span_ft),
        interior_reactions_lb=(1.1 * total_plf * span_ft, 1.1 * total_plf * span_ft),
        design_moment_type="negative" if moment_negative >= moment_positive else "positive",
        source=THREE_SPAN_SOURCE,
        positive_moment_inlb=moment_positive,
        negative_moment_inlb=moment_negative,
    )


def _coefficient_deflection(
    w_plf: float,
    span_ft: float,
    e_psi: float,
    ix_in4: float,
    coefficient: float,
) -> float:
    """Return deflection ``coefficient * w * L^4 / (E * I)`` in inches."""

    w_lbin = w_plf / 12.0
    span_in = span_ft * 12.0
    return coefficient * w_lbin * span_in**4 / (e_psi * ix_in4)
