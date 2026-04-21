"""Equivalent Lateral Force (ELF) seismic engine per ASCE 7-22 Chapter 12.

Scope (V1):
    * ELF procedure only — SDC A/B/C always; SDC D/E/F only when height ≤ 50 m
      and plan is regular. Outside that envelope the engine still returns a
      result but emits a P3W003 error-level warning.
    * Site coefficients F_a and F_v are taken from embedded lookup tables
      (ASCE 7-22 Tables 11.4-1 and 11.4-2).
    * Structural-system R, C_d, and Ω_0 are selected from material-family
      defaults; all values are recorded as overrideable assumptions.
"""

from __future__ import annotations

from typing import Any

from ..assumptions import AssumptionBuilder
from ..models.enums import MaterialFamily, RiskCategory, SeismicDesignCategory
from ..models.loads import SeismicLoadResult, StoryLoadResult
from ..models.outputs import Phase3Warning
from ..warnings import make_warning

# ---------------------------------------------------------------------------
# Site coefficient tables (embedded — ASCE 7-22 Tables 11.4-1 and 11.4-2).
# Keys are (site_class, S_threshold_upper); value is the coefficient.
# ---------------------------------------------------------------------------

#: ASCE 7-22 Table 11.4-1. Fa as a function of site class and mapped Ss.
FA_TABLE: dict[str, dict[float, float]] = {
    "A": {0.25: 0.8, 0.5: 0.8, 0.75: 0.8, 1.0: 0.8, 1.25: 0.8, float("inf"): 0.8},
    "B": {0.25: 0.9, 0.5: 0.9, 0.75: 0.9, 1.0: 0.9, 1.25: 0.9, float("inf"): 0.9},
    "C": {0.25: 1.3, 0.5: 1.3, 0.75: 1.2, 1.0: 1.2, 1.25: 1.2, float("inf"): 1.2},
    "D": {0.25: 1.6, 0.5: 1.4, 0.75: 1.2, 1.0: 1.1, 1.25: 1.0, float("inf"): 1.0},
    "E": {0.25: 2.4, 0.5: 1.7, 0.75: 1.3, 1.0: 1.1, 1.25: 0.9, float("inf"): 0.9},
}

#: ASCE 7-22 Table 11.4-2. Fv as a function of site class and mapped S1.
FV_TABLE: dict[str, dict[float, float]] = {
    "A": {0.10: 0.8, 0.20: 0.8, 0.30: 0.8, 0.40: 0.8, 0.50: 0.8, float("inf"): 0.8},
    "B": {0.10: 0.8, 0.20: 0.8, 0.30: 0.8, 0.40: 0.8, 0.50: 0.8, float("inf"): 0.8},
    "C": {0.10: 1.5, 0.20: 1.5, 0.30: 1.5, 0.40: 1.5, 0.50: 1.4, float("inf"): 1.4},
    "D": {0.10: 2.4, 0.20: 2.2, 0.30: 2.0, 0.40: 1.9, 0.50: 1.8, float("inf"): 1.7},
    "E": {0.10: 4.2, 0.20: 3.3, 0.30: 2.8, 0.40: 2.4, 0.50: 2.2, float("inf"): 2.0},
}

#: Conservative defaults when Ss / S1 are not supplied — representative of
#: higher-seismic western-US sites.
DEFAULT_SS: float = 1.5
DEFAULT_S1: float = 0.6

#: Minimum approximate fundamental period for Cs max cap when SDC >= E.
#: Not used directly; Ta is computed via Eq. 12.8-7.

#: Maximum height (m) for which ELF is permitted in SDC D/E/F without extra
#: height-limit checks.
ELF_HEIGHT_LIMIT_SDC_DEF_M: float = 50.0

#: Importance factor Ie for seismic per ASCE 7-22 Table 1.5-2.
IMPORTANCE_FACTOR_SEISMIC: dict[RiskCategory, float] = {
    RiskCategory.I: 1.00,
    RiskCategory.II: 1.00,
    RiskCategory.III: 1.25,
    RiskCategory.IV: 1.50,
}


def compute_seismic_loads(
    building_graph: dict[str, Any],
    structural_design_graph: dict[str, Any],
    story_loads: list[StoryLoadResult],
    *,
    material_family: MaterialFamily,
    risk_category: RiskCategory,
    site_class: str,
    Ss: float | None,
    S1: float | None,
    assumption_builder: AssumptionBuilder,
) -> tuple[SeismicLoadResult, list[Phase3Warning]]:
    """Compute ELF seismic loads for the building.

    Args:
        building_graph: Phase 1 BuildingGraph as a dict.
        structural_design_graph: Phase 2 StructuralDesignGraph as a dict.
        story_loads: Story load results (ordered roof to ground).
        material_family: Primary structural material family.
        risk_category: Risk category.
        site_class: Seismic site class.
        Ss: Mapped MCE_R short-period spectral acceleration (g) or None.
        S1: Mapped MCE_R 1-second spectral acceleration (g) or None.
        assumption_builder: Shared assumption builder.

    Returns:
        Tuple of (seismic result, warnings emitted).
    """

    warnings: list[Phase3Warning] = []
    assumption_ids: list[str] = []

    Ss_value, S1_value = _resolve_spectral(
        Ss, S1, assumption_builder, assumption_ids, warnings
    )
    site_class_upper = site_class.upper()
    Fa = _lookup_fa(site_class_upper, Ss_value)
    Fv = _lookup_fv(site_class_upper, S1_value)

    assumption_builder.add(
        id="seismic_site_class",
        name="Seismic site class",
        value=site_class_upper,
        unit=None,
        source="ASCE 7-22 Section 20.1 (default D when unknown)",
        confidence=0.80,
        rationale="Stiff-soil default; override with geotechnical data when available.",
        overrideable=True,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_site_class")

    assumption_builder.add(
        id="seismic_Fa",
        name="Site coefficient F_a",
        value=round(Fa, 3),
        unit="dimensionless",
        source="ASCE 7-22 Table 11.4-1",
        confidence=0.90,
        rationale=f"Interpolated table lookup for site class {site_class_upper}, Ss={Ss_value}.",
        overrideable=False,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_Fa")
    assumption_builder.add(
        id="seismic_Fv",
        name="Site coefficient F_v",
        value=round(Fv, 3),
        unit="dimensionless",
        source="ASCE 7-22 Table 11.4-2",
        confidence=0.90,
        rationale=f"Interpolated table lookup for site class {site_class_upper}, S1={S1_value}.",
        overrideable=False,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_Fv")

    SMS = Fa * Ss_value
    SM1 = Fv * S1_value
    SDS = (2.0 / 3.0) * SMS
    SD1 = (2.0 / 3.0) * SM1

    for name, val in [("SMS", SMS), ("SM1", SM1), ("SDS", SDS), ("SD1", SD1)]:
        aid = f"seismic_{name}"
        assumption_builder.add(
            id=aid,
            name=f"Design spectral acceleration {name}",
            value=round(val, 4),
            unit="g",
            source="ASCE 7-22 Eq. 11.4-1/2/3/4",
            confidence=0.95,
            rationale=f"{name} derived from Fa/Fv, Ss, S1.",
            overrideable=False,
            affects_modules=["seismic"],
        )
        assumption_ids.append(aid)

    sdc = _determine_sdc(SDS, SD1, risk_category)
    assumption_builder.add(
        id="seismic_design_category",
        name="Seismic Design Category",
        value=sdc.value,
        unit=None,
        source="ASCE 7-22 Tables 11.6-1 and 11.6-2",
        confidence=0.93,
        rationale="Most severe of the SDS- and SD1-based tables with risk category.",
        overrideable=False,
        affects_modules=["seismic", "combos"],
    )
    assumption_ids.append("seismic_design_category")

    # Structural system defaults
    height_m = float(building_graph.get("project", {}).get("total_height_mm", 0.0)) / 1000.0
    R, Cd, Omega0, system_name, Ct, x_exp = _structural_system_defaults(
        material_family=material_family,
        structural_design_graph=structural_design_graph,
        assumption_builder=assumption_builder,
        assumption_ids=assumption_ids,
    )

    # Height limit warning for SDC D/E/F
    if sdc in (SeismicDesignCategory.D, SeismicDesignCategory.E, SeismicDesignCategory.F):
        if height_m > ELF_HEIGHT_LIMIT_SDC_DEF_M:
            warnings.append(make_warning("P3W003"))

    # Ta per Eq. 12.8-7
    Ta = Ct * (max(height_m, 0.001)) ** x_exp
    assumption_builder.add(
        id="seismic_Ta",
        name="Approximate fundamental period T_a",
        value=round(Ta, 4),
        unit="s",
        source="ASCE 7-22 Eq. 12.8-7",
        confidence=0.85,
        rationale=f"Ta = {Ct} * {height_m:.2f}^{x_exp} = {Ta:.3f} s.",
        overrideable=True,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_Ta")

    Ie = IMPORTANCE_FACTOR_SEISMIC[risk_category]
    assumption_builder.add(
        id="seismic_importance_factor",
        name="Seismic importance factor Ie",
        value=Ie,
        unit="dimensionless",
        source="ASCE 7-22 Table 1.5-2",
        confidence=0.98,
        rationale=f"Risk category {risk_category.value} -> Ie = {Ie}.",
        overrideable=False,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_importance_factor")

    # Cs per Eqs. 12.8-2, 12.8-3, 12.8-5, 12.8-6
    Cs_calc = SDS / (R / Ie)
    Cs_max = SD1 / (Ta * (R / Ie)) if Ta > 0 else Cs_calc
    Cs_min1 = max(0.044 * SDS * Ie, 0.01)
    Cs_min2 = 0.5 * S1_value / (R / Ie) if S1_value >= 0.6 else 0.0
    Cs = max(min(Cs_calc, Cs_max), Cs_min1, Cs_min2)

    assumption_builder.add(
        id="seismic_Cs",
        name="Seismic response coefficient Cs",
        value=round(Cs, 5),
        unit="dimensionless",
        source="ASCE 7-22 Section 12.8.1",
        confidence=0.92,
        rationale=(
            f"Cs = max(min({Cs_calc:.4f}, {Cs_max:.4f}), {Cs_min1:.4f}, {Cs_min2:.4f})."
        ),
        overrideable=False,
        affects_modules=["seismic", "combos"],
    )
    assumption_ids.append("seismic_Cs")

    # Effective seismic weight W = sum of story weights
    W_kN = sum(sl.story_weight_kN for sl in story_loads)
    V_kN = Cs * W_kN

    assumption_builder.add(
        id="seismic_effective_weight_W",
        name="Effective seismic weight W",
        value=round(W_kN, 2),
        unit="kN",
        source="ASCE 7-22 Section 12.7.2",
        confidence=0.93,
        rationale="Sum of all story weights (dead + fractional live per Section 12.7.2).",
        overrideable=False,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_effective_weight_W")

    # Story force distribution per Eq. 12.8-11 / 12
    k = _distribution_exponent(Ta)
    story_forces_kN = _distribute_story_forces(story_loads, V_kN, k)

    assumption_builder.add(
        id="seismic_distribution_exponent_k",
        name="Seismic distribution exponent k",
        value=round(k, 3),
        unit="dimensionless",
        source="ASCE 7-22 Eq. 12.8-12",
        confidence=0.95,
        rationale=f"k interpolated for Ta={Ta:.2f} s: 1.0 for <=0.5 s, 2.0 for >=2.5 s.",
        overrideable=False,
        affects_modules=["seismic"],
    )
    assumption_ids.append("seismic_distribution_exponent_k")

    return (
        SeismicLoadResult(
            site_class=site_class_upper,
            risk_category=risk_category.value,
            importance_factor_seismic=Ie,
            Ss=Ss_value,
            S1=S1_value,
            Fa=Fa,
            Fv=Fv,
            SMS=SMS,
            SM1=SM1,
            SDS=SDS,
            SD1=SD1,
            seismic_design_category=sdc.value,
            R=R,
            Cd=Cd,
            Omega0=Omega0,
            Ta=Ta,
            Cs=Cs,
            W=W_kN,
            V=V_kN,
            story_forces=story_forces_kN,
            assumption_ids=assumption_ids,
        ),
        warnings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_spectral(
    Ss: float | None,
    S1: float | None,
    builder: AssumptionBuilder,
    ids: list[str],
    warnings: list[Phase3Warning],
) -> tuple[float, float]:
    """Return (Ss, S1), falling back to defaults and emitting a warning if used."""

    used_default = False
    ss_value = Ss
    s1_value = S1

    if ss_value is None:
        ss_value = DEFAULT_SS
        used_default = True
    if s1_value is None:
        s1_value = DEFAULT_S1
        used_default = True

    builder.add(
        id="seismic_Ss",
        name="Mapped MCE_R short-period spectral acceleration Ss",
        value=ss_value,
        unit="g",
        source=(
            "ASCE 7 Hazard Tool / user override"
            if Ss is not None
            else "Conservative default (Ss=1.5) for high-seismic western US"
        ),
        confidence=0.92 if Ss is not None else 0.45,
        rationale="Provided explicitly." if Ss is not None else "Default — override strongly recommended.",
        overrideable=True,
        affects_modules=["seismic", "combos"],
    )
    ids.append("seismic_Ss")

    builder.add(
        id="seismic_S1",
        name="Mapped MCE_R 1-second spectral acceleration S1",
        value=s1_value,
        unit="g",
        source=(
            "ASCE 7 Hazard Tool / user override"
            if S1 is not None
            else "Conservative default (S1=0.6) for high-seismic western US"
        ),
        confidence=0.92 if S1 is not None else 0.45,
        rationale="Provided explicitly." if S1 is not None else "Default — override strongly recommended.",
        overrideable=True,
        affects_modules=["seismic", "combos"],
    )
    ids.append("seismic_S1")

    if used_default:
        warnings.append(make_warning("P3W004"))

    return ss_value, s1_value


def _lookup_fa(site_class: str, Ss: float) -> float:
    """Step-through Fa lookup per ASCE 7-22 Table 11.4-1."""

    if site_class not in FA_TABLE:
        site_class = "D"
    row = FA_TABLE[site_class]
    for threshold in sorted(row.keys()):
        if Ss <= threshold:
            return row[threshold]
    return row[float("inf")]


def _lookup_fv(site_class: str, S1: float) -> float:
    """Step-through Fv lookup per ASCE 7-22 Table 11.4-2."""

    if site_class not in FV_TABLE:
        site_class = "D"
    row = FV_TABLE[site_class]
    for threshold in sorted(row.keys()):
        if S1 <= threshold:
            return row[threshold]
    return row[float("inf")]


def _determine_sdc(
    SDS: float, SD1: float, risk_category: RiskCategory
) -> SeismicDesignCategory:
    """Determine SDC per ASCE 7-22 Tables 11.6-1 and 11.6-2 — take more severe."""

    # Risk categories I, II, III
    low_risk = risk_category in (RiskCategory.I, RiskCategory.II, RiskCategory.III)

    if low_risk:
        # Table 11.6-1 (SDS)
        if SDS < 0.167:
            sdc_s = SeismicDesignCategory.A
        elif SDS < 0.33:
            sdc_s = SeismicDesignCategory.B
        elif SDS < 0.50:
            sdc_s = SeismicDesignCategory.C
        else:
            sdc_s = SeismicDesignCategory.D
        # Table 11.6-2 (SD1)
        if SD1 < 0.067:
            sdc_1 = SeismicDesignCategory.A
        elif SD1 < 0.133:
            sdc_1 = SeismicDesignCategory.B
        elif SD1 < 0.20:
            sdc_1 = SeismicDesignCategory.C
        else:
            sdc_1 = SeismicDesignCategory.D
    else:  # Risk IV
        if SDS < 0.167:
            sdc_s = SeismicDesignCategory.A
        elif SDS < 0.33:
            sdc_s = SeismicDesignCategory.C
        elif SDS < 0.50:
            sdc_s = SeismicDesignCategory.D
        else:
            sdc_s = SeismicDesignCategory.D
        if SD1 < 0.067:
            sdc_1 = SeismicDesignCategory.A
        elif SD1 < 0.133:
            sdc_1 = SeismicDesignCategory.C
        elif SD1 < 0.20:
            sdc_1 = SeismicDesignCategory.D
        else:
            sdc_1 = SeismicDesignCategory.D

    return max(sdc_s, sdc_1, key=lambda x: list(SeismicDesignCategory).index(x))


def _structural_system_defaults(
    *,
    material_family: MaterialFamily,
    structural_design_graph: dict[str, Any],
    assumption_builder: AssumptionBuilder,
    assumption_ids: list[str],
) -> tuple[float, float, float, str, float, float]:
    """Return (R, Cd, Omega0, system_label, Ct, x_exp) for the default system."""

    lateral_candidates = structural_design_graph.get("lateral_system_candidates") or []
    has_shear_walls = any(
        "shear_wall" in str(c.get("system_type", "")).lower()
        for c in lateral_candidates
    )

    if material_family == MaterialFamily.REINFORCED_CONCRETE:
        if has_shear_walls:
            R, Cd, Omega0 = 6.0, 5.0, 2.5
            label = "RC special reinforced shear walls"
            Ct, x_exp = 0.0488, 0.75
        else:
            R, Cd, Omega0 = 8.0, 5.5, 3.0
            label = "RC special moment frame"
            Ct, x_exp = 0.0466, 0.9
    elif material_family == MaterialFamily.STRUCTURAL_STEEL:
        R, Cd, Omega0 = 8.0, 5.5, 3.0
        label = "Steel special moment frame"
        Ct, x_exp = 0.0724, 0.8
    else:
        raise ValueError(f"Unsupported material family: {material_family}")

    aid = "seismic_structural_system"
    assumption_builder.add(
        id=aid,
        name="Default lateral structural system",
        value=label,
        unit=None,
        source="ASCE 7-22 Table 12.2-1",
        confidence=0.75,
        rationale=f"Default for {material_family.value}; R/Cd/Omega0 = {R}/{Cd}/{Omega0}.",
        overrideable=True,
        affects_modules=["seismic", "combos"],
    )
    assumption_ids.append(aid)

    for label_name, val, aid_name in [
        ("R", R, "seismic_R"),
        ("Cd", Cd, "seismic_Cd"),
        ("Omega0", Omega0, "seismic_Omega0"),
    ]:
        assumption_builder.add(
            id=aid_name,
            name=f"Response modification factor {label_name}",
            value=val,
            unit="dimensionless",
            source="ASCE 7-22 Table 12.2-1",
            confidence=0.85,
            rationale=f"{label_name} for {label}.",
            overrideable=True,
            affects_modules=["seismic", "combos"],
        )
        assumption_ids.append(aid_name)

    return R, Cd, Omega0, label, Ct, x_exp


def _distribution_exponent(Ta: float) -> float:
    """Interpolate k per ASCE 7-22 Eq. 12.8-12."""

    if Ta <= 0.5:
        return 1.0
    if Ta >= 2.5:
        return 2.0
    return 1.0 + (Ta - 0.5) / 2.0  # Linear interpolation


def _distribute_story_forces(
    story_loads: list[StoryLoadResult], V_kN: float, k: float
) -> dict[str, float]:
    """Distribute base shear to each story via Cvx = wx hx^k / Σ wi hi^k."""

    if V_kN <= 0 or not story_loads:
        return {sl.story_id: 0.0 for sl in story_loads}

    numerators = [sl.story_weight_kN * (max(sl.elevation_m, 0.001) ** k) for sl in story_loads]
    denom = sum(numerators)
    if denom <= 0:
        n = len(story_loads)
        return {sl.story_id: V_kN / n for sl in story_loads}

    return {
        sl.story_id: V_kN * num / denom
        for sl, num in zip(story_loads, numerators)
    }
