"""Core Building Graph schema — the single source of truth for all downstream modules.

Every input channel (structured form, CAD file, floor plan image) produces
an instance of ``BuildingGraph``.  All coordinates are in **millimeters**.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .assumptions import AssumptionRecord
from .enums import (
    BuildingType,
    CoreType,
    InputSource,
    MaterialPreference,
    OccupancyType,
    OpeningType,
    RoomType,
    WallType,
)
from .provenance import ProvenanceRecord

# ---------------------------------------------------------------------------
# Schema version — bump on any breaking change to BuildingGraph or its sub-
# models.  Persisted on every emitted graph so downstream consumers can detect
# version skew and refuse to proceed.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Project-level models
# ---------------------------------------------------------------------------

class Location(BaseModel):
    """Geographic location with optional environmental metadata."""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    seismic_zone: Optional[str] = None
    wind_speed_mph: Optional[float] = Field(default=None, ge=0)


class ProjectInfo(BaseModel):
    """Top-level project metadata."""

    name: str = Field(..., min_length=1, max_length=256)
    location: Location
    occupancy_type: OccupancyType
    material_preference: MaterialPreference
    num_stories: int = Field(..., ge=1, le=200)
    total_height_mm: float = Field(..., gt=0)
    building_code: Optional[str] = "IBC 2021"


# ---------------------------------------------------------------------------
# Structural / spatial models
# ---------------------------------------------------------------------------

class Story(BaseModel):
    """A single building storey."""

    id: str
    level: int
    floor_to_floor_mm: float = Field(..., ge=2400, le=20000)
    elevation_mm: float
    floor_area_gross_m2: float = Field(..., ge=0)
    floor_area_net_m2: Optional[float] = Field(default=None, ge=0)
    usage: str


class GridLine(BaseModel):
    """A single grid line along one axis."""

    id: str
    position_mm: float


class Bay(BaseModel):
    """A rectangular bay defined by four grid lines."""

    id: str
    span_x_mm: float = Field(..., gt=0)
    span_y_mm: float = Field(..., gt=0)
    grid_x_start: str
    grid_x_end: str
    grid_y_start: str
    grid_y_end: str


class GridSystem(BaseModel):
    """The structural grid: X and Y grid lines plus the bays they define."""

    x_lines: list[GridLine]
    y_lines: list[GridLine]
    bays: list[Bay]

    @field_validator("x_lines", "y_lines")
    @classmethod
    def lines_ascending(cls, v: list[GridLine]) -> list[GridLine]:
        for i in range(1, len(v)):
            if v[i].position_mm <= v[i - 1].position_mm:
                raise ValueError(
                    f"Grid lines must be in ascending order of position_mm; "
                    f"found {v[i - 1].position_mm} >= {v[i].position_mm}"
                )
        return v


class WallSegment(BaseModel):
    """A wall element defined by start/end points in mm."""

    id: str
    type: WallType
    start: list[float] = Field(..., min_length=2, max_length=2)
    end: list[float] = Field(..., min_length=2, max_length=2)
    thickness_mm: float = Field(..., gt=0)
    height_mm: Optional[float] = Field(default=None, gt=0)
    stories: list[str] = Field(..., min_length=1)
    material: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[ProvenanceRecord] = None


class Room(BaseModel):
    """A room or zone represented as a closed polygon."""

    id: str
    label: str
    type: RoomType
    polygon: list[list[float]]
    area_m2: float = Field(..., ge=0)
    story: str
    perimeter_mm: Optional[float] = Field(default=None, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("polygon")
    @classmethod
    def polygon_minimum_points(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        for pt in v:
            if len(pt) != 2:
                raise ValueError("Each polygon point must be [x, y]")
        return v


class Opening(BaseModel):
    """A door or window located along a wall segment."""

    id: str
    type: OpeningType
    wall_id: str
    position_mm: float = Field(..., ge=0)
    width_mm: float = Field(..., gt=0)
    height_mm: Optional[float] = Field(default=None, gt=0)
    sill_height_mm: Optional[float] = Field(default=None, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[ProvenanceRecord] = None


class ColumnCandidate(BaseModel):
    """A potential column location with confidence scoring."""

    position: list[float] = Field(..., min_length=2, max_length=2)
    grid_intersection: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_required: bool = False
    notes: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None


class Core(BaseModel):
    """A vertical-service core (elevator, stairs, MEP, etc.)."""

    id: str
    type: CoreType
    polygon: list[list[float]]
    contains_elevator: bool = False
    contains_stairs: bool = False
    stories: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[ProvenanceRecord] = None

    @field_validator("polygon")
    @classmethod
    def core_polygon_minimum(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) < 3:
            raise ValueError("Core polygon must have at least 3 points")
        return v


class Facade(BaseModel):
    """The building perimeter / facade."""

    perimeter_polygon: list[list[float]]
    perimeter_length_mm: float = Field(..., gt=0)

    @field_validator("perimeter_polygon")
    @classmethod
    def facade_polygon_minimum(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) < 3:
            raise ValueError("Facade polygon must have at least 3 points")
        return v


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class ConfidenceScores(BaseModel):
    """Per-subsystem confidence scores (0.0–1.0).

    These describe *how well* each detection subsystem performed.  Distinct
    from :class:`CompletenessScore`, which describes *how much* of the
    expected element budget was actually produced.
    """

    wall_detection: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    room_classification: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    grid_detection: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    dimension_extraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    opening_detection: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    column_inference: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    overall: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CompletenessScore(BaseModel):
    """How complete the Building Graph is, expressed as a 0.0–1.0 score.

    The completeness scorer (Phase 1) folds together: presence of grid lines,
    presence of facade polygon, ratio of openings detected to walls, presence
    of cores when the building is multi-story, and whether optional but
    high-value detectors (YOLO-Seg, symbol detector) participated in the run.

    Each field is independently meaningful; ``overall`` is the weighted
    average and is what the API gateway returns to the frontend.
    """

    overall: float = Field(..., ge=0.0, le=1.0)
    geometry: float = Field(..., ge=0.0, le=1.0)
    semantics: float = Field(..., ge=0.0, le=1.0)
    detector_coverage: float = Field(..., ge=0.0, le=1.0)
    missing_subsystems: list[str] = Field(default_factory=list)


class BuildingMetadata(BaseModel):
    """Provenance and quality metadata for a Building Graph."""

    job_id: Optional[str] = Field(default=None, max_length=128)
    input_source: InputSource
    inferred_building_type: Optional[BuildingType] = Field(
        default=None,
        description="High-level building family inferred by the VLM gap-filler",
    )
    confidence_scores: ConfidenceScores = Field(default_factory=ConfidenceScores)
    completeness: Optional[CompletenessScore] = None
    # Legacy free-form list — preserved for backward compatibility with
    # earlier graphs.  New producers SHOULD write to ``assumption_register``.
    assumptions_made: list[str] = Field(default_factory=list)
    assumption_register: list[AssumptionRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_time_seconds: Optional[float] = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Top-level Building Graph
# ---------------------------------------------------------------------------

class BuildingGraph(BaseModel):
    """The unified output of Phase 1.

    Every input channel produces this same schema.  This is the single source
    of truth that all downstream modules consume.
    """

    schema_version: str = Field(default=SCHEMA_VERSION)
    project: ProjectInfo
    stories: list[Story] = Field(..., min_length=1)
    grid: GridSystem
    walls: list[WallSegment]
    rooms: list[Room]
    openings: list[Opening] = Field(default_factory=list)
    column_candidates: list[ColumnCandidate]
    cores: list[Core] = Field(default_factory=list)
    facade: Facade
    metadata: BuildingMetadata

    @model_validator(mode="after")
    def stories_match_project(self) -> "BuildingGraph":
        if len(self.stories) != self.project.num_stories:
            raise ValueError(
                f"Number of stories ({len(self.stories)}) does not match "
                f"project.num_stories ({self.project.num_stories})"
            )
        return self
