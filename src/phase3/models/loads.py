"""Load-result Pydantic models for Phase 3.

All loads are expressed in SI units. Every numeric result is backed by one or
more ``AssumptionRecord`` entries in the assumption register, referenced via
``assumption_ids``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import LoadCombinationType, OccupancyCategory


class DeadLoadResult(BaseModel):
    """Dead load summary for a single story (or the building default)."""

    structural_self_weight_kPa: float = Field(..., ge=0.0)
    superimposed_dead_kPa: float = Field(..., ge=0.0)
    mep_allowance_kPa: float = Field(..., ge=0.0)
    partitions_kPa: float = Field(..., ge=0.0)
    cladding_kN_per_m: float = Field(..., ge=0.0)
    total_dead_kPa: float = Field(..., ge=0.0)
    assumption_ids: list[str] = Field(default_factory=list)


class LiveLoadResult(BaseModel):
    """Live load result for a single occupancy / support combination."""

    occupancy: OccupancyCategory
    unreduced_live_kPa: float = Field(..., ge=0.0)
    reduction_factor: float = Field(..., ge=0.0, le=1.0)
    reduced_live_kPa: float = Field(..., ge=0.0)
    reduction_applied: bool
    reduction_rationale: str
    support_id: str | None = None
    story_id: str | None = None
    assumption_ids: list[str] = Field(default_factory=list)


class TributaryAreaResult(BaseModel):
    """Tributary area for a single support on a single story."""

    support_id: str
    story_id: str
    tributary_area_m2: float = Field(..., ge=0.0)
    polygon_wkt: str
    is_edge_column: bool
    is_corner_column: bool
    is_interior_column: bool
    computation_method: str
    assumption_ids: list[str] = Field(default_factory=list)


class StoryLoadResult(BaseModel):
    """Aggregated vertical loads for one story, with cumulative totals."""

    story_id: str
    elevation_m: float
    floor_area_m2: float = Field(..., ge=0.0)
    total_dead_kN: float = Field(..., ge=0.0)
    total_live_kN: float = Field(..., ge=0.0)
    cumulative_dead_kN: float = Field(..., ge=0.0)
    cumulative_live_kN: float = Field(..., ge=0.0)
    story_weight_kN: float = Field(..., ge=0.0)
    assumption_ids: list[str] = Field(default_factory=list)


class WindLoadResult(BaseModel):
    """Results of the simplified Directional Procedure wind computation."""

    basic_wind_speed_m_per_s: float = Field(..., ge=0.0)
    exposure_category: str
    risk_category: str
    importance_factor_wind: float = Field(..., gt=0.0)
    velocity_pressure_kPa: float = Field(..., ge=0.0)
    windward_pressure_kPa: float
    leeward_pressure_kPa: float
    net_lateral_wind_kN: float = Field(..., ge=0.0)
    wind_base_shear_kN: float = Field(..., ge=0.0)
    story_wind_forces: dict[str, float] = Field(default_factory=dict)
    code_reference: str = "ASCE 7-22 Chapter 27 (Directional Procedure, simplified)"
    assumption_ids: list[str] = Field(default_factory=list)


class SeismicLoadResult(BaseModel):
    """Results of the Equivalent Lateral Force (ELF) seismic computation."""

    site_class: str
    risk_category: str
    importance_factor_seismic: float = Field(..., gt=0.0)
    Ss: float = Field(..., ge=0.0)
    S1: float = Field(..., ge=0.0)
    Fa: float = Field(..., gt=0.0)
    Fv: float = Field(..., gt=0.0)
    SMS: float = Field(..., ge=0.0)
    SM1: float = Field(..., ge=0.0)
    SDS: float = Field(..., ge=0.0)
    SD1: float = Field(..., ge=0.0)
    seismic_design_category: str
    R: float = Field(..., gt=0.0)
    Cd: float = Field(..., gt=0.0)
    Omega0: float = Field(..., gt=0.0)
    Ta: float = Field(..., gt=0.0)
    Cs: float = Field(..., gt=0.0)
    W: float = Field(..., ge=0.0)
    V: float = Field(..., ge=0.0)
    story_forces: dict[str, float] = Field(default_factory=dict)
    code_reference: str = "ASCE 7-22 Chapter 12 (ELF)"
    assumption_ids: list[str] = Field(default_factory=list)


class LoadCombinationResult(BaseModel):
    """A single evaluated LRFD load combination at a representative support."""

    combination_id: LoadCombinationType
    combination_label: str
    D: float
    L: float
    Lr: float
    W: float
    E: float
    factored_total: float
    governs: bool
    assumption_ids: list[str] = Field(default_factory=list)


class MemberLoadDemand(BaseModel):
    """Axial demand on a single support at a single story."""

    support_id: str
    story_id: str
    axial_dead_kN: float = Field(..., ge=0.0)
    axial_live_kN: float = Field(..., ge=0.0)
    axial_factored_kN: float
    governing_combination: LoadCombinationType
    cumulative_axial_kN: float
    assumption_ids: list[str] = Field(default_factory=list)
