"""Review-queue service — Step 11.

Phase 1 produces a Building Graph on every channel, but ML outputs
(Channel C) and some CAD edge cases leave individual elements with a
confidence low enough that a human should approve them before downstream
stages consume the graph.  This module is the thin domain layer that
powers the two review endpoints:

* ``GET  /api/v1/jobs/{job_id}/review`` — :func:`build_review_snapshot`
  pulls everything the review UI needs out of a graph in one pass:
  the completeness gate, low-confidence elements per kind, and the
  subset of the assumption register a reviewer can actually change.

* ``POST /api/v1/jobs/{job_id}/review`` — :func:`apply_corrections`
  merges reviewer edits back into the graph.  Every touched element
  has its ``confidence`` set to ``1.0`` and its ``provenance`` replaced
  with a :class:`DetectorSource.USER_OVERRIDE` record so any future
  consumer can tell human-approved data from ML output at a glance.

The service deliberately owns *only* graph-mutation logic.  The endpoint
layer handles routing, auth, and store plumbing; unit tests exercise
the service directly on synthetic graphs.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from pydantic import BaseModel

from src.core.provenance_helpers import user_override_provenance
from src.schema.assumptions import AssumptionRecord
from src.schema.building_graph import (
    BuildingGraph,
    ColumnCandidate,
    Core,
    Opening,
    Room,
    WallSegment,
)
from src.schema.enums import confidence_to_level
from src.schema.input_models import (
    CompletenessSnapshot,
    LowConfidenceElement,
    OverrideableAssumption,
    ReviewElementCorrection,
    ReviewSnapshotResponse,
)
from src.utils.completeness_scorer import HUMAN_REVIEW_THRESHOLD


# ---------------------------------------------------------------------------
# Snapshot (GET)
# ---------------------------------------------------------------------------


# Elements below this confidence are surfaced as low-confidence in the
# snapshot.  Deliberately aligned with the completeness review threshold so
# the "element is suspect" and "graph needs review" gates move together.
LOW_CONFIDENCE_THRESHOLD: float = HUMAN_REVIEW_THRESHOLD

_REVIEW_WARNING_PREFIX = "requires_human_review:"

# Explicit "the pipeline collapsed and produced a stand-in graph"
# signals.  These are emitted by the Channel-C image builder when the
# ML stack produces zero walls and it falls back to a schema-valid
# placeholder.  A graph carrying one of these MUST be reviewed even if
# its scalar completeness happens to land above the review threshold
# (the placeholder's synthesised stories and fallback rooms can inflate
# the overall score above 0.5 while walls / openings / columns are all
# empty — exactly the case a reviewer needs to see).
_HARD_REVIEW_MARKERS: frozenset[str] = frozenset(
    {
        "degraded_placeholder_graph_emitted",
        "image_pipeline_produced_no_walls",
    }
)


def _is_review_required(bg: BuildingGraph) -> bool:
    """Did the pipeline flag this graph for human review?

    Three independent signals, any one triggers the gate:

    1. ``metadata.completeness.overall`` below the review threshold
       (the primary quantitative signal, written by
       :func:`src.utils.completeness_scorer.annotate_with_completeness`).
    2. A ``requires_human_review:`` marker string already present in
       ``metadata.warnings``.  The scorer writes this whenever (1)
       trips, so graphs hydrated from a persisted store keep the flag
       even if the structured completeness field is stripped.
    3. One of the :data:`_HARD_REVIEW_MARKERS` (explicit "the pipeline
       collapsed" warnings from the image graph builder).  These
       catch the case where an ML failure produces a schema-valid but
       essentially-empty graph whose scalar completeness is misleadingly
       above the threshold.
    """

    score = bg.metadata.completeness
    if score is not None and score.overall < HUMAN_REVIEW_THRESHOLD:
        return True
    warnings = bg.metadata.warnings
    if any(w.startswith(_REVIEW_WARNING_PREFIX) for w in warnings):
        return True
    return any(w in _HARD_REVIEW_MARKERS for w in warnings)


def _wall_summary(w: WallSegment) -> str:
    length = (
        (w.end[0] - w.start[0]) ** 2 + (w.end[1] - w.start[1]) ** 2
    ) ** 0.5
    return f"{w.type.value} wall, {int(length)} mm, thickness {int(w.thickness_mm)} mm"


def _room_summary(r: Room) -> str:
    return f"{r.type.value} room '{r.label}' ({r.area_m2:.1f} m²)"


def _opening_summary(o: Opening) -> str:
    return f"{o.type.value} on {o.wall_id} @ {int(o.position_mm)} mm, width {int(o.width_mm)} mm"


def _column_summary(c: ColumnCandidate) -> str:
    tag = c.grid_intersection or f"({c.position[0]:.0f}, {c.position[1]:.0f})"
    return f"Column {tag}" + (" (required)" if c.is_required else " (candidate)")


def _core_summary(c: Core) -> str:
    flags = []
    if c.contains_elevator:
        flags.append("elevator")
    if c.contains_stairs:
        flags.append("stairs")
    tail = f" ({', '.join(flags)})" if flags else ""
    return f"{c.type.value} core{tail}"


def _detector_source(element: Any) -> Optional[str]:
    prov = getattr(element, "provenance", None)
    if prov is None:
        return None
    src = getattr(prov, "detector_source", None)
    return src.value if src is not None else None


def _collect_low_confidence(
    bg: BuildingGraph, *, threshold: float = LOW_CONFIDENCE_THRESHOLD
) -> list[LowConfidenceElement]:
    """Walk every element collection and bucket anything below threshold."""

    flagged: list[LowConfidenceElement] = []

    for w in bg.walls:
        if w.confidence < threshold:
            flagged.append(
                LowConfidenceElement(
                    kind="wall",
                    id=w.id,
                    confidence=float(w.confidence),
                    detector_source=_detector_source(w),
                    summary=_wall_summary(w),
                )
            )
    for r in bg.rooms:
        if r.confidence < threshold:
            flagged.append(
                LowConfidenceElement(
                    kind="room",
                    id=r.id,
                    confidence=float(r.confidence),
                    detector_source=_detector_source(r),
                    summary=_room_summary(r),
                )
            )
    for o in bg.openings:
        if o.confidence < threshold:
            flagged.append(
                LowConfidenceElement(
                    kind="opening",
                    id=o.id,
                    confidence=float(o.confidence),
                    detector_source=_detector_source(o),
                    summary=_opening_summary(o),
                )
            )
    for idx, c in enumerate(bg.column_candidates):
        if c.confidence < threshold:
            flagged.append(
                LowConfidenceElement(
                    kind="column",
                    id=str(idx),
                    confidence=float(c.confidence),
                    detector_source=_detector_source(c),
                    summary=_column_summary(c),
                )
            )
    for c in bg.cores:
        if c.confidence < threshold:
            flagged.append(
                LowConfidenceElement(
                    kind="core",
                    id=c.id,
                    confidence=float(c.confidence),
                    detector_source=_detector_source(c),
                    summary=_core_summary(c),
                )
            )
    return flagged


def _project_assumption(a: AssumptionRecord) -> OverrideableAssumption:
    return OverrideableAssumption(
        id=a.id,
        name=a.name,
        value=a.value,
        unit=a.unit,
        confidence=float(a.confidence),
        confidence_level=a.confidence_level.value,
        rationale=a.rationale,
        affects_modules=list(a.affects_modules),
        was_overridden=a.was_overridden,
        override_value=a.override_value,
        override_source=a.override_source,
    )


def _collect_overrideable_assumptions(
    bg: BuildingGraph,
) -> list[OverrideableAssumption]:
    """Return overrideable assumptions, lowest-confidence first."""

    rows = [
        _project_assumption(a)
        for a in bg.metadata.assumption_register
        if a.overrideable
    ]
    rows.sort(key=lambda r: (r.confidence, r.id))
    return rows


def _build_completeness_snapshot(bg: BuildingGraph) -> Optional[CompletenessSnapshot]:
    score = bg.metadata.completeness
    if score is None:
        return None
    return CompletenessSnapshot(
        overall=float(score.overall),
        geometry=float(score.geometry),
        semantics=float(score.semantics),
        detector_coverage=float(score.detector_coverage),
        missing_subsystems=list(score.missing_subsystems),
    )


def build_review_snapshot(
    *,
    job_id: str,
    status: str,
    bg: Optional[BuildingGraph],
) -> ReviewSnapshotResponse:
    """Snapshot everything the review UI needs in a single call.

    ``bg=None`` is a valid input: a job that's still processing / failed
    still gets a response so the UI can render a "not yet" state.  In
    that case ``review_required`` is ``False`` (no graph, nothing to
    review) and every collection is empty.
    """

    if bg is None:
        return ReviewSnapshotResponse(
            job_id=job_id,
            status=status,
            review_required=False,
            completeness=None,
            warnings=[],
            low_confidence_elements=[],
            overrideable_assumptions=[],
        )

    return ReviewSnapshotResponse(
        job_id=job_id,
        status=status,
        review_required=_is_review_required(bg),
        completeness=_build_completeness_snapshot(bg),
        warnings=list(bg.metadata.warnings),
        low_confidence_elements=_collect_low_confidence(bg),
        overrideable_assumptions=_collect_overrideable_assumptions(bg),
    )


# ---------------------------------------------------------------------------
# Corrections (POST)
# ---------------------------------------------------------------------------


class ReviewCorrectionError(ValueError):
    """Raised by :func:`apply_corrections` on any reviewer-addressable failure.

    The endpoint layer translates this to an HTTP 422.  Distinct from
    :class:`LookupError`, which :func:`apply_corrections` raises when
    an ``id`` / ``target`` tuple doesn't resolve to a real element — the
    endpoint translates those to 404.
    """


# Target name -> Building Graph attribute name + element model.  The
# service uses this to look up the right collection for each correction.
_TARGET_SCHEMA: dict[str, tuple[str, type[BaseModel]]] = {
    "wall": ("walls", WallSegment),
    "room": ("rooms", Room),
    "opening": ("openings", Opening),
    "column": ("column_candidates", ColumnCandidate),
    "core": ("cores", Core),
}

# Fields a reviewer can touch on each element type.  Confidence and
# provenance are service-managed — the reviewer doesn't get to set them
# directly — and id is immutable.  Anything else a reviewer submits is
# rejected with a 422 so a typo doesn't silently no-op.
_EDITABLE_FIELDS: dict[str, frozenset[str]] = {
    "wall": frozenset(
        {"type", "start", "end", "thickness_mm", "height_mm", "stories", "material"}
    ),
    "room": frozenset(
        {"label", "type", "polygon", "area_m2", "story", "perimeter_mm"}
    ),
    "opening": frozenset(
        {"type", "wall_id", "position_mm", "width_mm", "height_mm", "sill_height_mm"}
    ),
    "column": frozenset({"position", "grid_intersection", "is_required", "notes"}),
    "core": frozenset(
        {"type", "polygon", "contains_elevator", "contains_stairs", "stories"}
    ),
}


def _find_element(
    bg: BuildingGraph, target: str, element_id: str
) -> tuple[str, int, BaseModel]:
    """Resolve a (target, id) pair to (attr_name, index, element)."""

    if target not in _TARGET_SCHEMA:
        raise ReviewCorrectionError(
            f"Unknown correction target {target!r}; "
            f"expected one of {sorted(_TARGET_SCHEMA)}."
        )
    attr, _ = _TARGET_SCHEMA[target]
    collection: list[BaseModel] = getattr(bg, attr)

    if target == "column":
        try:
            idx = int(element_id)
        except ValueError as exc:
            raise ReviewCorrectionError(
                f"Column corrections must use an integer index as id; got {element_id!r}."
            ) from exc
        if idx < 0 or idx >= len(collection):
            raise LookupError(
                f"No column candidate at index {idx} (have {len(collection)})."
            )
        return attr, idx, collection[idx]

    for i, elem in enumerate(collection):
        if getattr(elem, "id", None) == element_id:
            return attr, i, elem

    raise LookupError(f"No {target} with id {element_id!r} in the graph.")


def _merge_element(
    existing: BaseModel,
    *,
    target: str,
    fields: dict[str, Any],
    run_id: str,
    reviewer: Optional[str],
) -> BaseModel:
    """Re-validate a merged element and stamp user-override provenance.

    Validation is delegated to pydantic: we ``model_validate`` a dict
    built from the existing element plus the reviewer's fields.  The
    returned model is a brand-new instance so the caller is free to
    swap it into the list in-place.
    """

    unknown = set(fields) - _EDITABLE_FIELDS[target]
    if unknown:
        raise ReviewCorrectionError(
            f"Unknown or non-editable field(s) for target {target!r}: "
            f"{sorted(unknown)}.  Editable fields: "
            f"{sorted(_EDITABLE_FIELDS[target])}."
        )

    existing_dict = existing.model_dump()
    prior_detector = None
    prior_prov = existing_dict.get("provenance")
    if isinstance(prior_prov, dict):
        prior_detector = prior_prov.get("detector_source")

    merged = {**existing_dict, **fields}
    merged["confidence"] = 1.0
    notes = "human review correction"
    if reviewer:
        notes = f"{notes} by {reviewer}"
    if prior_detector:
        notes = f"{notes}; prior source={prior_detector}"
    merged["provenance"] = user_override_provenance(
        run_id=run_id, notes=notes
    ).model_dump()

    cls = type(existing)
    try:
        return cls.model_validate(merged)
    except Exception as exc:  # pydantic.ValidationError or friends
        raise ReviewCorrectionError(
            f"Correction produced an invalid {target}: {exc}"
        ) from exc


def apply_corrections(
    bg: BuildingGraph,
    corrections: Iterable[ReviewElementCorrection],
    *,
    run_id: str,
    reviewer: Optional[str] = None,
) -> list[str]:
    """Merge a batch of reviewer corrections into ``bg`` in-place.

    Semantics:

    * Each correction is applied in the order given.  We stop at the
      first failure — caller decides whether to roll the graph back or
      leave partial progress for the reviewer to continue with.  (The
      endpoint layer leaves partial progress committed, mirroring the
      existing override behaviour.)
    * ``bg`` is mutated in place: matching list entries are replaced
      with a new model instance that carries the merged fields,
      ``confidence=1.0``, and a ``user_override`` provenance record.
    * Returns a list of ``"<target>:<id>"`` tags identifying the
      elements that were successfully edited, in the order they were
      applied.  Useful for structured logging.

    Raises :class:`LookupError` when a target element is missing (the
    endpoint translates this to 404) and :class:`ReviewCorrectionError`
    for everything else (422).
    """

    applied: list[str] = []
    for correction in corrections:
        attr, idx, existing = _find_element(bg, correction.target, correction.id)
        updated = _merge_element(
            existing,
            target=correction.target,
            fields=correction.fields,
            run_id=run_id,
            reviewer=reviewer,
        )
        collection: list[BaseModel] = getattr(bg, attr)
        collection[idx] = updated
        applied.append(f"{correction.target}:{correction.id}")
    return applied


__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "ReviewCorrectionError",
    "apply_corrections",
    "build_review_snapshot",
]
