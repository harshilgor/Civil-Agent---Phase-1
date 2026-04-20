"""Simplified directional-procedure wind load engine.

Implements ASCE 7-22 Chapter 27 for regular rectangular buildings with mean
roof height ≤ 60 m. Out-of-scope buildings still return a result, but emit a
P3W001 warning so the user knows the simplified procedure may not apply.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from ..assumptions import AssumptionBuilder
from ..models.enums import ExposureCategory, RiskCategory
from ..models.loads import WindLoadResult
from ..models.outputs import Phase3Warning
from ..warnings import make_warning

#: Maximum building height (m) for which the simplified approach is considered
#: applicable in Phase 3 V1.
SIMPLIFIED_WIND_HEIGHT_LIMIT_M: float = 60.0

#: Default basic wind speed (m/s) when no site-specific value is provided.
#: 40 m/s ≈ 90 mph — conservative continental-US default.
DEFAULT_BASIC_WIND_SPEED_M_S: float = 40.0

#: Velocity-pressure coefficient table parameters per exposure
#: (ASCE 7-22 Table 26.10-1: zg in m, α dimensionless, K_z floor).
EXPOSURE_PARAMETERS: dict[ExposureCategory, dict[str, float]] = {
    ExposureCategory.B: {"zg_m": 365.8, "alpha": 7.0, "kz_min": 0.70},
    ExposureCategory.C: {"zg_m": 274.3, "alpha": 9.5, "kz_min": 0.85},
    ExposureCategory.D: {"zg_m": 213.4, "alpha": 11.5, "kz_min": 1.03},
}

#: Topographic factor; 1.0 means no topographic amplification (default).
KZT_DEFAULT: float = 1.0

#: Wind directionality factor for buildings (ASCE 7-22 Table 26.6-1).
KD_BUILDINGS: float = 0.85

#: Gust-effect factor for rigid buildings (ASCE 7-22 Section 26.11.4).
GUST_FACTOR_RIGID: float = 0.85

#: Windward external pressure coefficient Cp (ASCE 7-22 Figure 27.3-1).
CP_WINDWARD: float = 0.80

#: Leeward external pressure coefficient for L/B in [0, 1] (conservative).
CP_LEEWARD: float = -0.50

#: Enclosed-building internal pressure coefficient magnitude.
GCPI_ENCLOSED: float = 0.18

#: Importance factor table for wind per ASCE 7-22 Table 1.5-2.
IMPORTANCE_FACTOR_WIND: dict[RiskCategory, float] = {
    RiskCategory.I: 0.87,
    RiskCategory.II: 1.00,
    RiskCategory.III: 1.15,
    RiskCategory.IV: 1.15,
}


def compute_wind_loads(
    building_graph: dict[str, Any],
    *,
    basic_wind_speed_m_per_s: float | None,
    exposure_category: ExposureCategory,
    risk_category: RiskCategory,
    assumption_builder: AssumptionBuilder,
) -> tuple[WindLoadResult, list[Phase3Warning]]:
    """Compute simplified wind loads for the building.

    Args:
        building_graph: Phase 1 BuildingGraph as a dict.
        basic_wind_speed_m_per_s: User-supplied wind speed, or ``None`` to use
            the conservative default.
        exposure_category: Wind exposure category.
        risk_category: Risk category for importance factor lookup.
        assumption_builder: Shared assumption builder.

    Returns:
        Tuple of (wind load result, warnings emitted by this engine).
    """

    warnings: list[Phase3Warning] = []
    assumption_ids: list[str] = []

    project = building_graph.get("project") or {}
    height_m = float(project.get("total_height_mm", 0.0)) / 1000.0
    if height_m <= 0:
        height_m = _estimate_height_from_stories(building_graph)

    if height_m > SIMPLIFIED_WIND_HEIGHT_LIMIT_M:
        warnings.append(make_warning("P3W001"))

    B_m, L_m = _building_plan_dimensions_m(building_graph)

    V_m_s = _basic_wind_speed(
        basic_wind_speed_m_per_s, assumption_builder, assumption_ids, warnings
    )
    exposure_params = EXPOSURE_PARAMETERS[exposure_category]
    Kz = _velocity_pressure_coefficient(height_m, exposure_params, assumption_builder, assumption_ids, exposure_category)
    Kzt = _register_constant(
        "wind_topographic_factor_Kzt", "Topographic factor K_zt", KZT_DEFAULT,
        unit="dimensionless",
        source="ASCE 7-22 Section 26.8.2 (no topographic amplification assumed)",
        confidence=0.85,
        rationale="No topographic data; assume flat site. Override near hills/escarpments.",
        overrideable=True,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )
    Kd = _register_constant(
        "wind_directionality_factor_Kd", "Wind directionality factor K_d", KD_BUILDINGS,
        unit="dimensionless",
        source="ASCE 7-22 Table 26.6-1",
        confidence=0.98,
        rationale="Standard value for buildings (MWFRS).",
        overrideable=False,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )

    # Velocity pressure q_z per ASCE 7-22 Eq. 26.10-1 (SI form).
    qz_kPa = 0.613 * Kz * Kzt * Kd * V_m_s * V_m_s / 1000.0
    assumption_builder.add(
        id="wind_velocity_pressure_qz",
        name="Velocity pressure q_z at mean roof height",
        value=round(qz_kPa, 4),
        unit="kPa",
        source="ASCE 7-22 Eq. 26.10-1 (SI): qz = 0.613 Kz Kzt Kd V^2",
        confidence=0.93,
        rationale=(
            f"q_z = 0.613 x {Kz:.3f} x {Kzt} x {Kd} x {V_m_s:.2f}^2 = {qz_kPa*1000:.1f} Pa."
        ),
        overrideable=False,
        affects_modules=["wind"],
    )
    assumption_ids.append("wind_velocity_pressure_qz")

    G = _register_constant(
        "wind_gust_factor_G", "Gust-effect factor G (rigid building)", GUST_FACTOR_RIGID,
        unit="dimensionless",
        source="ASCE 7-22 Section 26.11.4",
        confidence=0.90,
        rationale="Rigid-building assumption (natural frequency >= 1 Hz).",
        overrideable=True,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )
    Cp_windward = _register_constant(
        "wind_Cp_windward", "External pressure coefficient Cp (windward)", CP_WINDWARD,
        unit="dimensionless",
        source="ASCE 7-22 Figure 27.3-1",
        confidence=0.95,
        rationale="Standard MWFRS windward wall value.",
        overrideable=False,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )
    Cp_leeward = _register_constant(
        "wind_Cp_leeward", "External pressure coefficient Cp (leeward)", CP_LEEWARD,
        unit="dimensionless",
        source="ASCE 7-22 Figure 27.3-1 (L/B in [0, 1])",
        confidence=0.90,
        rationale="Conservative leeward value for near-square footprints.",
        overrideable=False,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )
    GCpi = _register_constant(
        "wind_GCpi_enclosed", "Internal pressure coefficient |GCpi| (enclosed)", GCPI_ENCLOSED,
        unit="dimensionless",
        source="ASCE 7-22 Table 26.13-1 (enclosed)",
        confidence=0.93,
        rationale="Enclosed-building assumption; worst-case direction applied to windward wall.",
        overrideable=True,
        affects_modules=["wind"],
        builder=assumption_builder,
        ids=assumption_ids,
    )

    # Windward pressure uses +GCpi (adds suction internally), leeward uses -GCpi.
    p_windward_kPa = qz_kPa * G * Cp_windward + qz_kPa * GCpi
    p_leeward_kPa = qz_kPa * G * Cp_leeward - qz_kPa * GCpi
    net_lateral_pressure_kPa = p_windward_kPa - p_leeward_kPa

    Ie = IMPORTANCE_FACTOR_WIND[risk_category]
    assumption_builder.add(
        id="wind_importance_factor",
        name="Wind importance factor Ie",
        value=Ie,
        unit="dimensionless",
        source="ASCE 7-22 Table 1.5-2",
        confidence=0.98,
        rationale=f"Risk category {risk_category.value} -> Ie = {Ie}.",
        overrideable=False,
        affects_modules=["wind"],
    )
    assumption_ids.append("wind_importance_factor")

    story_forces_kN, base_shear_kN = _story_wind_forces(
        building_graph=building_graph,
        B_m=B_m,
        net_lateral_pressure_kPa=net_lateral_pressure_kPa,
        Ie=Ie,
    )

    return (
        WindLoadResult(
            basic_wind_speed_m_per_s=V_m_s,
            exposure_category=exposure_category.value,
            risk_category=risk_category.value,
            importance_factor_wind=Ie,
            velocity_pressure_kPa=qz_kPa,
            windward_pressure_kPa=p_windward_kPa,
            leeward_pressure_kPa=p_leeward_kPa,
            net_lateral_wind_kN=net_lateral_pressure_kPa * B_m * height_m * Ie,
            wind_base_shear_kN=base_shear_kN,
            story_wind_forces=story_forces_kN,
            assumption_ids=assumption_ids,
        ),
        warnings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _basic_wind_speed(
    provided: float | None,
    builder: AssumptionBuilder,
    ids: list[str],
    warnings: list[Phase3Warning],
) -> float:
    value = provided if provided is not None else DEFAULT_BASIC_WIND_SPEED_M_S
    source = (
        "User-supplied basic wind speed"
        if provided is not None
        else "ASCE 7-22 Figure 26.5-1A conservative default"
    )
    builder.add(
        id="basic_wind_speed",
        name="Basic wind speed V",
        value=value,
        unit="m/s",
        source=source,
        confidence=0.90 if provided is not None else 0.55,
        rationale=(
            "Site-specific V provided by caller."
            if provided is not None
            else "No V provided; using 40 m/s (~90 mph) conservative default."
        ),
        overrideable=True,
        affects_modules=["wind"],
    )
    ids.append("basic_wind_speed")
    if provided is None:
        warnings.append(make_warning("P3W005"))
    return value


def _velocity_pressure_coefficient(
    z_m: float,
    params: dict[str, float],
    builder: AssumptionBuilder,
    ids: list[str],
    exposure: ExposureCategory,
) -> float:
    """Compute K_z via ASCE 7-22 Table 26.10-1 power law."""

    z_m = max(z_m, 4.6)  # Minimum height of 15 ft
    zg = params["zg_m"]
    alpha = params["alpha"]
    kz_raw = 2.01 * (z_m / zg) ** (2.0 / alpha)
    kz = max(kz_raw, params["kz_min"])

    builder.add(
        id="wind_velocity_pressure_coefficient_Kz",
        name="Velocity pressure exposure coefficient K_z",
        value=round(kz, 4),
        unit="dimensionless",
        source=f"ASCE 7-22 Table 26.10-1, Exposure {exposure.value}",
        confidence=0.95,
        rationale=(
            f"K_z = max(2.01 * (z/zg)^(2/alpha), K_z,min) with z={z_m:.2f} m, zg={zg}, "
            f"alpha={alpha}, floor={params['kz_min']}."
        ),
        overrideable=False,
        affects_modules=["wind"],
    )
    ids.append("wind_velocity_pressure_coefficient_Kz")
    return kz


def _register_constant(
    assumption_id: str,
    name: str,
    value: float,
    *,
    unit: str | None,
    source: str,
    confidence: float,
    rationale: str,
    overrideable: bool,
    affects_modules: list[str],
    builder: AssumptionBuilder,
    ids: list[str],
) -> float:
    """Register a named constant and append its id to the local tracking list."""

    if not builder.has(assumption_id):
        builder.add(
            id=assumption_id,
            name=name,
            value=value,
            unit=unit,
            source=source,
            confidence=confidence,
            rationale=rationale,
            overrideable=overrideable,
            affects_modules=affects_modules,
        )
    ids.append(assumption_id)
    return value


def _story_wind_forces(
    *,
    building_graph: dict[str, Any],
    B_m: float,
    net_lateral_pressure_kPa: float,
    Ie: float,
) -> tuple[dict[str, float], float]:
    """Distribute wind pressure to each story using tributary height."""

    stories = sorted(
        building_graph.get("stories") or [],
        key=lambda s: float(s.get("elevation_mm", 0.0)),
    )
    if not stories:
        return {}, 0.0

    forces: dict[str, float] = {}
    base_shear = 0.0
    for i, story in enumerate(stories):
        h_story_m = float(story.get("floor_to_floor_mm", 0.0)) / 1000.0
        h_upper = (
            float(stories[i + 1].get("floor_to_floor_mm", 0.0)) / 1000.0
            if i + 1 < len(stories)
            else 0.0
        )
        tributary_h_m = 0.5 * (h_story_m + h_upper) if h_upper else h_story_m
        force_kN = net_lateral_pressure_kPa * B_m * tributary_h_m * Ie
        forces[str(story.get("id"))] = force_kN
        base_shear += force_kN
    return forces, base_shear


def _building_plan_dimensions_m(building_graph: dict[str, Any]) -> tuple[float, float]:
    """Return a (B, L) pair of plan dimensions in meters from the facade bbox.

    B is the shorter plan dimension; L is the longer. Returns (0, 0) when no
    facade polygon is present.
    """

    facade = building_graph.get("facade") or {}
    pts = facade.get("perimeter_polygon") or []
    if len(pts) < 3:
        return 0.0, 0.0
    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        minx, miny, maxx, maxy = poly.bounds
        w_m = (maxx - minx) / 1000.0
        h_m = (maxy - miny) / 1000.0
        return min(w_m, h_m), max(w_m, h_m)
    except (ValueError, TypeError):
        return 0.0, 0.0


def _estimate_height_from_stories(building_graph: dict[str, Any]) -> float:
    """Fallback: estimate height from per-story floor-to-floor heights."""

    stories = building_graph.get("stories") or []
    return sum(float(s.get("floor_to_floor_mm", 0.0)) for s in stories) / 1000.0
