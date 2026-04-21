"""API request / response models.

These wrap the core Building Graph schema with request-specific metadata
(job IDs, timestamps, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


class ReviewElementCorrection(BaseModel):
    """A single human correction applied to a :class:`BuildingGraph` element.

    Step 11 extends the review endpoint beyond assumption-register overrides
    so a reviewer can also fix a concrete element the ML pipeline got wrong
    — a misclassified wall type, a mislabelled room, a door that the
    symbol detector put on the wrong wall, etc.

    Each correction identifies:

    * **target** — which collection in the graph the element lives on
      (``wall`` → ``walls``, ``room`` → ``rooms``, ``opening`` →
      ``openings``, ``column`` → ``column_candidates``, ``core`` →
      ``cores``).  Columns are identified by index (they don't have
      first-class ids); everything else is looked up by ``id``.
    * **id** — the element id for walls/rooms/openings/cores, or the
      column-candidates list index (as a string) for columns.
    * **fields** — a dict of field-name → replacement value.  Only the
      fields actually supplied are touched; absent fields are left alone.
      Validation is deferred to the pydantic re-parse inside the service
      layer so bad values get a 422 before the graph is mutated.

    The service layer stamps every touched element with
    :func:`src.core.provenance_helpers.user_override_provenance`
    (``DetectorSource.USER_OVERRIDE``, ``confidence_from_model=1.0``) and
    sets ``confidence=1.0``, so downstream stages can distinguish human
    corrections from any surviving ML confidence numbers.
    """

    target: Literal["wall", "room", "opening", "column", "core"] = Field(
        ...,
        description=(
            "Which Building Graph collection the element lives on.  "
            "Maps 1:1 to the schema field names."
        ),
    )
    id: str = Field(
        ...,
        min_length=1,
        description=(
            "Element id (walls/rooms/openings/cores) or stringified "
            "list index (columns)."
        ),
    )
    fields: dict[str, Any] = Field(
        ...,
        min_length=1,
        description=(
            "Field replacements.  Keys must correspond to writable fields "
            "on the target schema; unknown keys raise 422."
        ),
    )


class JobReviewRequest(BaseModel):
    """Payload for ``POST /api/v1/jobs/{job_id}/review``.

    Accepts two kinds of human input on the same request:

    * ``overrides`` — assumption-register overrides (Step 4 contract,
      preserved as-is).
    * ``corrections`` — element-level edits (Step 11 addition).

    At least one of the two must be non-empty.  Both are applied in
    order (overrides first, then corrections) so an assumption override
    can't conflict with a concrete element the reviewer also just edited.
    """

    overrides: list[AssumptionReviewItem] = Field(
        default_factory=list,
        description="Assumption overrides to apply (may be empty when only corrections are supplied).",
    )
    corrections: list[ReviewElementCorrection] = Field(
        default_factory=list,
        description="Element-level corrections to merge into the graph.",
    )
    reviewer: Optional[str] = Field(
        default=None,
        max_length=256,
        description=(
            "Optional reviewer identity appended to every override's ``source`` "
            "field so the audit trail records who approved each change."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> "JobReviewRequest":
        if not self.overrides and not self.corrections:
            raise ValueError(
                "JobReviewRequest must contain at least one of "
                "'overrides' or 'corrections'."
            )
        return self


# ---------------------------------------------------------------------------
# Review snapshot (GET /api/v1/jobs/{job_id}/review)
# ---------------------------------------------------------------------------


class LowConfidenceElement(BaseModel):
    """Compact summary of a single Building Graph element flagged for review.

    Emitted by the review-snapshot endpoint for every wall / room / opening
    / column / core whose ``confidence`` falls below the review threshold
    (``0.5`` by default, aligned with
    :data:`~src.utils.completeness_scorer.HUMAN_REVIEW_THRESHOLD`).  The
    frontend uses these to highlight the elements a reviewer should look
    at first; the full element object is still available via the graph.
    """

    kind: Literal["wall", "room", "opening", "column", "core"]
    id: str = Field(
        ...,
        description="Element id for walls/rooms/openings/cores; stringified index for columns.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    detector_source: Optional[str] = Field(
        default=None,
        description="``DetectorSource`` value from the element's provenance record, if present.",
    )
    summary: str = Field(
        ...,
        max_length=256,
        description=(
            "Human-readable tag (e.g. ``'STRUCTURAL wall 3200 mm long'``) "
            "so the review UI can render a row without re-parsing the graph."
        ),
    )


class OverrideableAssumption(BaseModel):
    """Compact projection of an :class:`AssumptionRecord` for the review UI.

    The snapshot endpoint filters the full register down to entries the
    reviewer can actually act on (``overrideable=True``) and sorts them by
    confidence ascending, so the most uncertain defaults float to the top.
    """

    id: str
    name: str
    value: Any
    unit: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: str
    rationale: str
    affects_modules: list[str] = Field(default_factory=list)
    was_overridden: bool = False
    override_value: Optional[Any] = None
    override_source: Optional[str] = None


class CompletenessSnapshot(BaseModel):
    """Flat projection of :class:`~src.schema.building_graph.CompletenessScore`."""

    overall: float = Field(..., ge=0.0, le=1.0)
    geometry: float = Field(..., ge=0.0, le=1.0)
    semantics: float = Field(..., ge=0.0, le=1.0)
    detector_coverage: float = Field(..., ge=0.0, le=1.0)
    missing_subsystems: list[str] = Field(default_factory=list)


class ReviewSnapshotResponse(BaseModel):
    """Response body of ``GET /api/v1/jobs/{job_id}/review``.

    Single round-trip snapshot of everything the review UI needs:

    * ``review_required`` — the completeness gate: ``True`` when overall
      completeness is below :data:`HUMAN_REVIEW_THRESHOLD` *or* the
      completeness scorer wrote a ``requires_human_review:`` marker onto
      ``metadata.warnings``.  The frontend uses this to decide whether
      to route the job straight to the reviewer queue.
    * ``completeness`` — the structured score so the UI can show a
      per-axis breakdown without re-running the scorer.
    * ``warnings`` — pass-through of ``metadata.warnings``; already
      includes the completeness scorer's missing-field tags.
    * ``low_confidence_elements`` — every wall / room / opening / column
      / core with ``confidence < 0.5``, bucketed so the UI can group
      them per kind.
    * ``overrideable_assumptions`` — the subset of the assumption
      register the reviewer can actually tune, sorted by confidence
      ascending (weakest first).
    """

    job_id: str
    status: str = Field(..., description="Job status at the time the snapshot was taken.")
    review_required: bool
    completeness: Optional[CompletenessSnapshot] = Field(
        default=None,
        description="``None`` on jobs that haven't finished producing a graph yet.",
    )
    warnings: list[str] = Field(default_factory=list)
    low_confidence_elements: list[LowConfidenceElement] = Field(default_factory=list)
    overrideable_assumptions: list[OverrideableAssumption] = Field(default_factory=list)


