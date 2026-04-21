"""Phase 2 Structural Design Graph schema.

This is the output of Phase 2 (the Structural Abstraction Engine) and the
input to Phase 3+. It is a **searchable design space** — it does NOT choose
a final structural system, size members, or compute loads. Instead it
encodes:

  * where structure can go (support candidates, zones)
  * where structure cannot go (forbidden regions)
  * which systems remain plausible (gravity + lateral candidates)
  * every constraint the later optimizer must respect

All coordinates are in millimeters and are defined in the same frame as the
source ``BuildingGraph``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.schema.structural_enums import (
    ConstraintPriority,
    ConstraintType,
    ForbiddenReason,
    FramingDirection,
    GravitySystemType,
    LateralSystemType,
    StructuralZoneType,
    SupportCandidateClass,
    SupportCandidateReason,
)


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


class StructuralZone(BaseModel):
    id: str
    type: StructuralZoneType
    polygon: list[list[float]]
    story: str
    area_m2: float = Field(..., ge=0)
    notes: str = ""


# ---------------------------------------------------------------------------
# Supports
# ---------------------------------------------------------------------------


class SupportCandidate(BaseModel):
    id: str
    position: list[float] = Field(..., min_length=2, max_length=2)
    story: str
    classification: SupportCandidateClass
    score: float = Field(..., ge=0.0, le=1.0)
    reasons: list[SupportCandidateReason] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    grid_intersection: Optional[str] = None
    is_stacked: bool = False
    stack_group_id: Optional[str] = None


class ForbiddenRegion(BaseModel):
    id: str
    polygon: list[list[float]]
    story: str
    reason: ForbiddenReason
    notes: str = ""


class VerticalAlignmentGroup(BaseModel):
    id: str
    support_ids: list[str]
    stories: list[str]
    alignment_quality: float = Field(..., ge=0.0, le=1.0)
    offset_mm: float = Field(default=0.0, ge=0.0)
    has_transfer: bool = False
    transfer_story: Optional[str] = None


# ---------------------------------------------------------------------------
# Spans / Framing
# ---------------------------------------------------------------------------


class SpanInfo(BaseModel):
    bay_id: str
    span_x_mm: float = Field(..., gt=0)
    span_y_mm: float = Field(..., gt=0)
    aspect_ratio: float = Field(..., ge=1.0)  # long/short, always >= 1
    classification: str
    support_start: str
    support_end: str


class SpanMap(BaseModel):
    spans: list[SpanInfo] = Field(default_factory=list)
    max_span_mm: float = 0.0
    min_span_mm: float = 0.0
    typical_span_mm: float = 0.0
    span_regularity: float = Field(default=1.0, ge=0.0)


class FramingZone(BaseModel):
    zone_id: str
    primary_direction: FramingDirection
    secondary_direction: FramingDirection
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------


class GravitySystemCandidate(BaseModel):
    system_type: GravitySystemType
    plausibility: float = Field(..., ge=0.0, le=1.0)
    applicable_zones: list[str] = Field(default_factory=list)
    rationale: str = ""
    limitations: list[str] = Field(default_factory=list)


class LateralSystemCandidate(BaseModel):
    system_type: LateralSystemType
    zone_id: str
    polygon: list[list[float]] = Field(default_factory=list)
    plausibility: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""
    symmetry_contribution: str = ""


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


class StructuralConstraint(BaseModel):
    id: str
    type: ConstraintType
    region: Optional[list[list[float]]] = None
    story: Optional[str] = None
    value: Optional[float] = None
    priority: ConstraintPriority = ConstraintPriority.SOFT
    source: str = ""
    rationale: str = ""


# ---------------------------------------------------------------------------
# Metadata + top-level graph
# ---------------------------------------------------------------------------


class StructuralMetadata(BaseModel):
    processing_time_seconds: float = Field(default=0.0, ge=0.0)
    assumptions_made: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_overall: float = Field(default=0.0, ge=0.0, le=1.0)
    building_regularity: str = "regular"  # "regular" | "mostly_regular" | "irregular"
    recommended_review_items: list[str] = Field(default_factory=list)


class StructuralDesignGraph(BaseModel):
    """Output of Phase 2 — the searchable structural design space."""

    building_graph_id: str
    zones: list[StructuralZone] = Field(default_factory=list)
    support_candidates: list[SupportCandidate] = Field(default_factory=list)
    forbidden_regions: list[ForbiddenRegion] = Field(default_factory=list)
    vertical_alignment_groups: list[VerticalAlignmentGroup] = Field(default_factory=list)
    span_map: SpanMap = Field(default_factory=SpanMap)
    framing_zones: list[FramingZone] = Field(default_factory=list)
    gravity_system_candidates: list[GravitySystemCandidate] = Field(default_factory=list)
    lateral_system_candidates: list[LateralSystemCandidate] = Field(default_factory=list)
    constraints: list[StructuralConstraint] = Field(default_factory=list)
    metadata: StructuralMetadata = Field(default_factory=StructuralMetadata)
