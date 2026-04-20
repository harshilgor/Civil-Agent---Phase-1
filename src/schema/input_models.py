"""API request / response models.

These wrap the core Building Graph schema with request-specific metadata
(job IDs, timestamps, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .building_graph import BuildingGraph, Location
from .enums import MaterialPreference, OccupancyType, RoofType


# ---------------------------------------------------------------------------
# Channel A — Structured form input
# ---------------------------------------------------------------------------

class CorePlacement(BaseModel):
    """User-specified core/service zone location."""

    x_start_mm: float
    y_start_mm: float
    x_end_mm: float
    y_end_mm: float
    contains_elevator: bool = True
    contains_stairs: bool = True


class StructuredInputRequest(BaseModel):
    """Everything needed to build a Building Graph from form parameters."""

    # Project identity
    project_name: str = Field(..., min_length=1, max_length=256)
    location: Location

    # Building envelope
    length_mm: float = Field(..., gt=0, description="Building length (X direction)")
    width_mm: float = Field(..., gt=0, description="Building width (Y direction)")
    num_stories: int = Field(..., ge=1, le=200)
    floor_to_floor_mm: float = Field(default=3900, ge=2400, le=20000)
    ground_floor_height_mm: Optional[float] = Field(
        default=None, ge=2400, le=20000,
        description="Override height for level 0 (often taller lobby)",
    )

    # Classification
    occupancy_type: OccupancyType = OccupancyType.OFFICE
    material_preference: MaterialPreference = MaterialPreference.REINFORCED_CONCRETE
    building_code: Optional[str] = "IBC 2021"

    # Grid preferences
    preferred_bay_x_mm: float = Field(default=8000, gt=0)
    preferred_bay_y_mm: float = Field(default=8000, gt=0)
    min_bay_mm: float = Field(default=4000, gt=0)
    max_bay_mm: float = Field(default=15000, gt=0)

    # Constraints
    x_constraints: list[float] = Field(
        default_factory=list,
        description="Fixed X positions (mm) that must be grid lines",
    )
    y_constraints: list[float] = Field(
        default_factory=list,
        description="Fixed Y positions (mm) that must be grid lines",
    )
    core_placements: list[CorePlacement] = Field(default_factory=list)

    # Roof
    roof_type: RoofType = RoofType.FLAT

    # Per-floor usage overrides (level → usage label)
    occupancy_by_floor: Optional[dict[int, str]] = None

    # Optimization hints (free-form tags consumed by downstream layers)
    optimization_hints: list[str] = Field(default_factory=list)


class GridModificationRequest(BaseModel):
    """Request body for ``PUT /api/v1/building/{project_id}/grid``."""

    preferred_bay_x_mm: Optional[float] = Field(default=None, gt=0)
    preferred_bay_y_mm: Optional[float] = Field(default=None, gt=0)
    min_bay_mm: Optional[float] = Field(default=None, gt=0)
    max_bay_mm: Optional[float] = Field(default=None, gt=0)
    x_constraints: Optional[list[float]] = None
    y_constraints: Optional[list[float]] = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class BuildingGraphResponse(BaseModel):
    """Standard response wrapping a Building Graph with request metadata."""

    project_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    building_graph: BuildingGraph


class CADUploadResponse(BaseModel):
    """Returned immediately when a CAD file is submitted for processing."""

    job_id: str
    status: str = "processing"
    filename: str
    file_type: str
    message: str = "File uploaded successfully. Processing started."


class ImageUploadResponse(BaseModel):
    """Returned immediately when a floor-plan image is submitted."""

    job_id: str
    status: str = "processing"
    filename: str
    message: str = "Image uploaded successfully. CV pipeline started."


class JobStatusResponse(BaseModel):
    """Polling endpoint response for async processing jobs."""

    job_id: str
    status: str  # queued | processing | completed | failed
    progress_percent: float = Field(default=0, ge=0, le=100)
    result_id: Optional[str] = None
    error: Optional[str] = None
    building_graph: Optional[BuildingGraph] = Field(
        default=None,
        description=(
            "Populated on status=completed so the frontend can fetch "
            "status and result in one round-trip."
        ),
    )


# ---------------------------------------------------------------------------
# Assumption override / review
# ---------------------------------------------------------------------------


class AssumptionOverrideRequest(BaseModel):
    """Payload for ``POST /api/v1/building/{project_id}/assumptions/{id}/override``."""

    value: object = Field(..., description="Replacement value for the assumption")
    source: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Who/what is providing the override (e.g. 'reviewer:jdoe').",
    )


class AssumptionReviewItem(BaseModel):
    """Single entry in the bulk-review payload."""

    assumption_id: str = Field(..., min_length=1)
    value: object
    source: str = Field(..., min_length=1, max_length=256)


class JobReviewRequest(BaseModel):
    """Payload for ``POST /api/v1/jobs/{job_id}/review``."""

    overrides: list[AssumptionReviewItem] = Field(
        ...,
        min_length=1,
        description="Non-empty list of assumption overrides to apply.",
    )
    reviewer: Optional[str] = Field(
        default=None,
        max_length=256,
        description=(
            "Optional reviewer identity appended to every override's ``source`` "
            "field so the audit trail records who approved each change."
        ),
    )


