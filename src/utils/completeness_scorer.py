"""Building Graph completeness scorer (Gap 8).

Evaluates how fully populated a ``BuildingGraph`` is after processing. Each
top-level section contributes a weighted sub-score; the weighted sum is the
overall completeness. Sections that are missing or under-populated produce
human-readable warnings and a ``missing_fields`` list for downstream
triage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.schema.building_graph import BuildingGraph, CompletenessScore
from src.schema.enums import DetectorSource, InputSource
from src.utils.geometry import polygon_area_mm2


# ---------------------------------------------------------------------------
# Per-channel detector expectations.
#
# The completeness scorer penalises an element subsystem only when the input
# channel is *expected* to have populated it.  For Channel A (structured
# form) and Channel B (parsed CAD / IFC) the user supplies every element
# directly — there is no ML detector that could have produced openings,
# column candidates, or fine-grained cores, so their absence on those
# channels is a by-design omission, not a deficit.  Channel C (CV pipeline)
# is the only one that pays the cost when an optional detector didn't run.
#
# Callers that need the element in every graph (e.g. geometry closure) keep
# scoring normally; this set governs only the *detector_coverage* axis and
# the ``missing_subsystems`` list on :class:`CompletenessScore`.
# ---------------------------------------------------------------------------

_USER_AUTHORITATIVE_CHANNELS: frozenset[InputSource] = frozenset(
    {
        InputSource.STRUCTURED_FORM,
        InputSource.DXF_FILE,
        InputSource.DWG_FILE,
        InputSource.IFC_FILE,
    }
)


def _is_user_authoritative(bg: BuildingGraph) -> bool:
    return bg.metadata.input_source in _USER_AUTHORITATIVE_CHANNELS


# Section weights — must sum to 1.0
_WEIGHTS: dict[str, float] = {
    "project_info": 0.05,
    "stories": 0.10,
    "grid": 0.15,
    "walls": 0.20,
    "rooms": 0.15,
    "openings": 0.10,
    "column_candidates": 0.10,
    "cores": 0.05,
    "facade": 0.10,
}


@dataclass
class CompletenessReport:
    overall_completeness: float
    section_scores: dict[str, float] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_completeness": round(self.overall_completeness, 3),
            "section_scores": {k: round(v, 3) for k, v in self.section_scores.items()},
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
        }


class CompletenessScorer:
    """Compute a structured completeness report for a ``BuildingGraph``."""

    def score(self, bg: BuildingGraph) -> CompletenessReport:
        missing: list[str] = []
        warnings: list[str] = []
        sections: dict[str, float] = {}

        sections["project_info"] = self._score_project(bg, missing)
        sections["stories"] = self._score_stories(bg, missing, warnings)
        sections["grid"] = self._score_grid(bg, warnings)
        sections["walls"] = self._score_walls(bg, missing, warnings)
        sections["rooms"] = self._score_rooms(bg, missing, warnings)
        sections["openings"] = self._score_openings(bg, warnings, missing)
        sections["column_candidates"] = self._score_columns(bg, warnings)
        sections["cores"] = self._score_cores(bg, warnings)
        sections["facade"] = self._score_facade(bg, missing, warnings)

        overall = sum(sections[k] * _WEIGHTS[k] for k in sections)
        return CompletenessReport(
            overall_completeness=overall,
            section_scores=sections,
            missing_fields=missing,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Section scorers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_project(bg: BuildingGraph, missing: list[str]) -> float:
        required = [
            ("project.name", bg.project.name),
            ("project.location", bg.project.location),
            ("project.occupancy_type", bg.project.occupancy_type),
            ("project.material_preference", bg.project.material_preference),
            ("project.num_stories", bg.project.num_stories),
            ("project.total_height_mm", bg.project.total_height_mm),
        ]
        missing_here = [name for name, v in required if v is None]
        missing.extend(missing_here)
        return max(0.0, 1.0 - 0.2 * len(missing_here))

    @staticmethod
    def _score_stories(
        bg: BuildingGraph, missing: list[str], warnings: list[str]
    ) -> float:
        if not bg.stories:
            warnings.append("No stories defined")
            return 0.0
        all_good = True
        for i, s in enumerate(bg.stories):
            if s.floor_to_floor_mm is None or s.floor_to_floor_mm <= 0:
                missing.append(f"stories[{i}].floor_to_floor_mm")
                all_good = False
            if s.elevation_mm is None:
                missing.append(f"stories[{i}].elevation_mm")
                all_good = False
            if s.floor_area_gross_m2 is None or s.floor_area_gross_m2 <= 0:
                missing.append(f"stories[{i}].floor_area_gross_m2")
                all_good = False
        return 1.0 if all_good else 0.6

    @staticmethod
    def _score_grid(bg: BuildingGraph, warnings: list[str]) -> float:
        g = bg.grid
        if not g.x_lines and not g.y_lines:
            warnings.append("No grid detected")
            return 0.0
        has_bays = bool(g.bays)
        if len(g.x_lines) >= 2 and len(g.y_lines) >= 2 and has_bays:
            if len(g.bays) == 1:
                warnings.append("Grid has only 1 bay")
            return 1.0
        if g.x_lines and g.y_lines and not has_bays:
            warnings.append("Grid lines present but no bays computed")
            return 0.5
        return 0.0

    @staticmethod
    def _score_walls(bg: BuildingGraph, missing: list[str], warnings: list[str]) -> float:
        walls = bg.walls
        if not walls:
            warnings.append("No walls detected")
            return 0.0
        count_score = 0.3
        thickness_ok = all(w.thickness_mm and w.thickness_mm > 0 for w in walls)
        type_ok = all(w.type is not None for w in walls)
        closure_score = _walls_form_closed_perimeter(bg) * 0.3

        for i, w in enumerate(walls):
            if not w.thickness_mm:
                missing.append(f"walls[{i}].thickness_mm")
        return count_score + (0.2 if thickness_ok else 0.0) + (0.2 if type_ok else 0.0) + closure_score

    @staticmethod
    def _score_rooms(bg: BuildingGraph, missing: list[str], warnings: list[str]) -> float:
        rooms = bg.rooms
        if not rooms:
            warnings.append("No rooms detected")
            return 0.0
        label_ok = all(r.label for r in rooms)
        type_ok = all(r.type is not None for r in rooms)
        closed_ok = all(_polygon_closed(r.polygon) for r in rooms)
        for i, r in enumerate(rooms):
            if not r.label:
                missing.append(f"rooms[{i}].label")
            if not _polygon_closed(r.polygon):
                missing.append(f"rooms[{i}].polygon (not closed)")
        return 0.3 + (0.2 if label_ok else 0.0) + (0.2 if type_ok else 0.0) + (0.3 if closed_ok else 0.0)

    @staticmethod
    def _score_openings(
        bg: BuildingGraph, warnings: list[str], missing: list[str]
    ) -> float:
        openings = bg.openings
        if not openings:
            if _is_user_authoritative(bg):
                # Channel A / B never enumerate doors & windows; absence is a
                # by-design omission, not a detection failure.  The graph is
                # still considered complete on this axis so the review gate
                # doesn't flag a clean structured-form submission.
                return 1.0
            # Channel C (CV pipeline) genuinely should have produced openings
            # if the symbol detector ran.
            warnings.append("No openings (doors/windows) detected")
            missing.append("openings (symbol_detector did not contribute)")
            return 0.0
        associated = all(o.wall_id and o.wall_id != "unknown" for o in openings)
        return 1.0 if associated else 0.5

    @staticmethod
    def _score_columns(bg: BuildingGraph, warnings: list[str]) -> float:
        if not bg.column_candidates:
            warnings.append("No column candidates identified")
            return 0.0
        has_confidence = all(c.confidence is not None for c in bg.column_candidates)
        return 1.0 if has_confidence else 0.5

    @staticmethod
    def _score_cores(bg: BuildingGraph, warnings: list[str]) -> float:
        if bg.cores:
            return 1.0
        # Check whether the building should have had a core
        has_core_rooms = any(
            r.type.value in {"STAIRWELL", "ELEVATOR"} for r in bg.rooms
        )
        if has_core_rooms:
            warnings.append("Stair/elevator rooms present but no core zone identified")
            return 0.5
        return 1.0  # absence is fine for single-story / low-rise

    @staticmethod
    def _score_facade(bg: BuildingGraph, missing: list[str], warnings: list[str]) -> float:
        f = bg.facade
        if not f or not f.perimeter_polygon:
            missing.append("facade.perimeter_polygon")
            warnings.append("Facade missing")
            return 0.0
        if not _polygon_closed(f.perimeter_polygon):
            missing.append("facade.perimeter_polygon (not closed)")
            return 0.5
        return 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _polygon_closed(pts: list[list[float]] | None) -> bool:
    if not pts or len(pts) < 3:
        return False
    return pts[0] == pts[-1]


def _walls_form_closed_perimeter(bg: BuildingGraph) -> float:
    """Heuristic: return 1.0 if there are at least 4 FACADE-type walls, else 0."""
    facade_walls = [w for w in bg.walls if w.type.value == "FACADE"]
    return 1.0 if len(facade_walls) >= 4 else 0.0


# ---------------------------------------------------------------------------
# Integration helper — attach report to a BuildingGraph's metadata
# ---------------------------------------------------------------------------


HUMAN_REVIEW_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# CompletenessScore bridge
#
# The legacy ``CompletenessReport`` carries a flat ``overall_completeness``
# scalar plus free-form missing-field / warning lists.  The Step-2 schema
# upgraded metadata to carry a *structured* :class:`CompletenessScore`
# (overall / geometry / semantics / detector_coverage + missing_subsystems);
# this section bridges the two.  We fold the nine section scores into three
# aggregates the optimiser and review UI actually reason about:
#
# * ``geometry``         — grid + walls + facade.  Is the physical shape
#                          of the building fully reconstructed?
# * ``semantics``        — rooms + stories + project.  Do the elements have
#                          the labels and relationships required downstream?
# * ``detector_coverage`` — openings + columns + cores.  Which optional
#                          detectors actually ran and produced output for
#                          this graph?  (YOLO-Seg / symbol detector absence
#                          lowers this axis without failing the pipeline.)
# ---------------------------------------------------------------------------

_GEOMETRY_SECTIONS = ("grid", "walls", "facade")
_SEMANTICS_SECTIONS = ("project_info", "stories", "rooms")
_DETECTOR_SECTIONS = ("openings", "column_candidates", "cores")


def _aggregate(sections: dict[str, float], keys: tuple[str, ...]) -> float:
    total = 0.0
    weight = 0.0
    for k in keys:
        w = _WEIGHTS.get(k, 0.0)
        total += sections.get(k, 0.0) * w
        weight += w
    return total / weight if weight > 0 else 0.0


def _collect_missing_subsystems(bg: BuildingGraph, report: CompletenessReport) -> list[str]:
    """Flag detector subsystems that produced nothing for this graph.

    Only the CV pipeline (Channel C) is expected to invoke ML detectors, so
    this list stays empty for user-authoritative channels (STRUCTURED_FORM /
    DXF_FILE / DWG_FILE / IFC_FILE) regardless of whether the graph happens
    to contain openings or columns.  A Channel-A submission that legitimately
    has no doors and no user-supplied columns is not missing a detector —
    no detector was ever expected to run.

    For Channel C, flags come from two places:

    1. Whole sections that scored zero (``_score_openings`` /
       ``_score_columns`` emit "No openings detected" or "No column
       candidates identified").
    2. Provenance inspection (future): elements stamped by the CubiCasa
       hourglass without matching openings imply the symbol detector did
       not run.

    The list is human-readable detector-source names (matching the
    :class:`DetectorSource` enum values), which is what the Phase-3
    assumption-confidence adjuster expects.
    """

    if _is_user_authoritative(bg):
        return []

    missing: list[str] = []
    section_scores = report.section_scores

    if section_scores.get("openings", 0.0) == 0.0 and not bg.openings:
        # No openings at all -> neither YOLO nor the symbol detector
        # contributed to this graph.
        missing.append(DetectorSource.SYMBOL_DETECTOR.value)
    if section_scores.get("column_candidates", 0.0) == 0.0 and not bg.column_candidates:
        missing.append(DetectorSource.YOLO_SEG.value)

    # De-dup while preserving insertion order.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in missing:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def build_completeness_score(bg: BuildingGraph) -> CompletenessScore:
    """Fold the nine-section :class:`CompletenessReport` into a
    :class:`CompletenessScore` suitable for ``BuildingMetadata.completeness``.
    """

    report = CompletenessScorer().score(bg)
    sections = report.section_scores
    return CompletenessScore(
        overall=report.overall_completeness,
        geometry=_aggregate(sections, _GEOMETRY_SECTIONS),
        semantics=_aggregate(sections, _SEMANTICS_SECTIONS),
        detector_coverage=_aggregate(sections, _DETECTOR_SECTIONS),
        missing_subsystems=_collect_missing_subsystems(bg, report),
    )


def annotate_with_completeness(bg: BuildingGraph) -> BuildingGraph:
    """Compute completeness and store it on ``bg.metadata``.

    Populates both the legacy scalar
    (``metadata.confidence_scores.overall``) and the Step-2 structured
    :class:`CompletenessScore` (``metadata.completeness``).  Also toggles a
    ``requires_human_review`` warning when overall completeness is below
    ``HUMAN_REVIEW_THRESHOLD``.
    """
    report = CompletenessScorer().score(bg)
    bg.metadata.confidence_scores.overall = report.overall_completeness
    bg.metadata.completeness = CompletenessScore(
        overall=report.overall_completeness,
        geometry=_aggregate(report.section_scores, _GEOMETRY_SECTIONS),
        semantics=_aggregate(report.section_scores, _SEMANTICS_SECTIONS),
        detector_coverage=_aggregate(report.section_scores, _DETECTOR_SECTIONS),
        missing_subsystems=_collect_missing_subsystems(bg, report),
    )
    for w in report.warnings:
        if w not in bg.metadata.warnings:
            bg.metadata.warnings.append(w)
    for m in report.missing_fields:
        tag = f"missing_field: {m}"
        if tag not in bg.metadata.warnings:
            bg.metadata.warnings.append(tag)
    if report.overall_completeness < HUMAN_REVIEW_THRESHOLD:
        marker = "requires_human_review: overall completeness below 0.5"
        if marker not in bg.metadata.warnings:
            bg.metadata.warnings.append(marker)
    return bg


__all__ = [
    "CompletenessReport",
    "CompletenessScorer",
    "HUMAN_REVIEW_THRESHOLD",
    "annotate_with_completeness",
    "build_completeness_score",
]
