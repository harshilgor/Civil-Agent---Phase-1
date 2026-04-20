"""Top-level output models for Phase 3."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .assumptions import AssumptionRecord
from .enums import ConfidenceLevel, WarningLevel
from .loads import (
    DeadLoadResult,
    LiveLoadResult,
    LoadCombinationResult,
    MemberLoadDemand,
    SeismicLoadResult,
    StoryLoadResult,
    TributaryAreaResult,
    WindLoadResult,
)


class Phase3Warning(BaseModel):
    """A single structured warning emitted by Phase 3."""

    code: str
    level: WarningLevel
    message: str
    affected_module: str
    affected_element_ids: list[str] = Field(default_factory=list)
    recommendation: str


class AssumptionRegister(BaseModel):
    """The full set of assumptions made during a Phase 3 run."""

    total_count: int
    overridden_count: int
    low_confidence_count: int
    records: list[AssumptionRecord]

    def get_by_id(self, assumption_id: str) -> Optional[AssumptionRecord]:
        """Return the assumption with the given id, or None."""

        return next((r for r in self.records if r.id == assumption_id), None)

    def get_by_module(self, module: str) -> list[AssumptionRecord]:
        """Return all assumptions that affect the given downstream module."""

        return [r for r in self.records if module in r.affects_modules]


class DesignLoadModel(BaseModel):
    """The final load model for a single building.

    Downstream consumer: Phase 4 (Candidate Design Generator).
    """

    building_graph_id: str
    structural_graph_id: str
    building_code: str = "ASCE 7-22"
    dead_loads: DeadLoadResult
    live_loads: list[LiveLoadResult]
    tributary_areas: list[TributaryAreaResult]
    story_loads: list[StoryLoadResult]
    wind_loads: WindLoadResult
    seismic_loads: SeismicLoadResult
    load_combinations: list[LoadCombinationResult]
    member_demands: list[MemberLoadDemand]
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    overall_confidence_level: ConfidenceLevel


class Phase3Output(BaseModel):
    """Top-level Phase 3 API response."""

    status: str = Field(..., description="'success' | 'partial' | 'failed'")
    design_load_model: Optional[DesignLoadModel] = None
    assumption_register: AssumptionRegister
    warnings: list[Phase3Warning] = Field(default_factory=list)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    overall_confidence_level: ConfidenceLevel
    processing_time_seconds: float = Field(..., ge=0.0)
    computed_at: datetime
    phase3_version: str = "1.0.0"
