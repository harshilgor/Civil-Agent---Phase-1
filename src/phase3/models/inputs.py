"""Input models for Phase 3 requests."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .enums import ExposureCategory, MaterialFamily, RiskCategory


class LocationData(BaseModel):
    """Geographic location of the project site."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    city: str
    state_or_region: str
    country: str = "US"
    elevation_m: float = 0.0


class OverrideEntry(BaseModel):
    """A single user-supplied override for an assumption."""

    assumption_id: str
    new_value: Any
    provided_by: str = "user"
    justification: Optional[str] = None


class Phase3Input(BaseModel):
    """Top-level Phase 3 request payload.

    ``building_graph`` and ``structural_design_graph`` are accepted as dicts
    to avoid tight coupling to the Phase 1/2 schema versions; Phase 3 only
    relies on a defined subset of fields and validates them on the way in.
    """

    building_graph: dict[str, Any] = Field(
        ..., description="Validated BuildingGraph serialized to a dict"
    )
    structural_design_graph: dict[str, Any] = Field(
        ..., description="Validated StructuralDesignGraph serialized to a dict"
    )
    location: LocationData
    material_family: MaterialFamily
    risk_category: RiskCategory = RiskCategory.II
    exposure_category: ExposureCategory = ExposureCategory.C
    basic_wind_speed_m_per_s: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="If None, a conservative default is used",
    )
    site_class: str = Field(
        default="D",
        description="Seismic site class A–F; 'D' is ASCE 7-22 default when unknown",
    )
    Ss: Optional[float] = Field(
        default=None, ge=0.0, description="Mapped MCE_R short-period spectral acceleration"
    )
    S1: Optional[float] = Field(
        default=None, ge=0.0, description="Mapped MCE_R 1-second spectral acceleration"
    )
    overrides: list[OverrideEntry] = Field(default_factory=list)
    building_code: str = "ASCE 7-22"
