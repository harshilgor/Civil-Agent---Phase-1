"""JSON-serialisable calculation trace data structures."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceValue(BaseModel):
    """A value used in a calculation with its source citation."""

    name: str
    value: float | int | str | bool
    unit: str | None = None
    source: str
    confidence: str | None = None


class LoadTrace(BaseModel):
    """A load component or derived line/point load with source."""

    name: str
    value: float
    unit: str
    source: str
    load_type: str | None = None


class AdjustmentFactorTrace(BaseModel):
    """One NDS adjustment factor applied to an adjusted design value."""

    symbol: str
    name: str
    value: float
    applies_to: list[str]
    source: str
    confidence: str | None = None
    note: str | None = None


class CodeCheck(BaseModel):
    """A demand/capacity code check for one member and one limit state."""

    name: str
    demand: float
    capacity: float
    unit: str
    ratio: float
    passed: bool
    source: str
    equation: str
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectionTrace(BaseModel):
    """A pre-engineered connector selection trace."""

    interface: str
    demand_lb: float
    product: str
    allowable_load_lb: float
    utilisation: float
    source: str
    note: str
    warning: str | None = None


class MaterialSpec(BaseModel):
    """Material and section selected for a member."""

    material_type: Literal["sawn_lumber", "glulam", "lvl", "concrete"]
    species: str | None = None
    grade: str | None = None
    nominal_size: str | None = None
    actual_width_in: float | None = None
    actual_depth_in: float | None = None


class CalculationTrace(BaseModel):
    """Full trace for a single member sizing operation."""

    member_id: str
    member_type: str
    material: MaterialSpec
    span_ft: float | None = None
    length_ft: float | None = None
    spacing_in: float | None = None
    span_config: str | None = None
    span_count: int | None = None
    interior_support_reactions: list[float] = Field(default_factory=list)
    design_moment_type: str | None = None
    header_load_condition: str | None = None
    rough_opening_ft: float | None = None
    wall_thickness: str | None = None
    tributary_width_ft: float | None = None
    jack_studs_required: int | None = None
    bearing_length_in: float | None = None
    loads: list[LoadTrace] = Field(default_factory=list)
    section_properties: list[SourceValue] = Field(default_factory=list)
    reference_design_values: list[SourceValue] = Field(default_factory=list)
    adjusted_design_values: list[SourceValue] = Field(default_factory=list)
    adjustment_factors: list[AdjustmentFactorTrace] = Field(default_factory=list)
    checks: list[CodeCheck] = Field(default_factory=list)
    connections: dict[str, ConnectionTrace] = Field(default_factory=dict)
    selection_mode: str = "user_declared"
    catalogue_note: str = ""
    auto_upsized: bool = False
    auto_upsize_reason: str = ""
    minimum_passing_member: str = ""
    governing_check: str | None = None
    final_utilization: float = 0.0
    warning: str | None = None
    passed: bool = False
    assumptions: list[str] = Field(default_factory=list)


class MemberResult(BaseModel):
    """Selected member result returned by the sizing engine."""

    member_id: str
    member_type: str
    selected: bool
    material: MaterialSpec
    span_ft: float | None = None
    length_ft: float | None = None
    spacing_in: float | None = None
    quantity: int = 1
    trace: CalculationTrace


class QuantitySummary(BaseModel):
    """High-level material quantities for one layout."""

    lumber_volume_ft3: float = 0.0
    glulam_volume_ft3: float = 0.0
    concrete_volume_ft3: float = 0.0
    joist_count: int = 0
    footing_count: int = 0
    span_count: int = 1


class AssumptionRecord(BaseModel):
    """Project-level or engine-level assumption surfaced in output."""

    description: str
    source: str


class DesignResult(BaseModel):
    """Complete JSON-serialisable sizing output for one layout."""

    model_config = ConfigDict(extra="forbid")

    project_name: str
    layout: str
    members: list[MemberResult]
    summary: QuantitySummary
    assumptions: list[AssumptionRecord]
    questions: list[str] = Field(default_factory=list)
