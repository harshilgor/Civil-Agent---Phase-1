"""Unit tests for :mod:`src.core.review_service`.

Exercises the service directly on synthetic :class:`BuildingGraph`
fixtures — no FastAPI, no Celery.  End-to-end coverage over the review
endpoints lives in :mod:`tests.test_api.test_jobs_review`.
"""

from __future__ import annotations

import pytest

from src.core.review_service import (
    LOW_CONFIDENCE_THRESHOLD,
    ReviewCorrectionError,
    apply_corrections,
    build_review_snapshot,
)
from src.schema.assumptions import AssumptionRecord
from src.schema.building_graph import (
    BuildingGraph,
    ColumnCandidate,
    Core,
    CompletenessScore,
    Opening,
    Room,
    WallSegment,
)
from src.schema.enums import (
    CoreType,
    DetectorSource,
    OpeningType,
    RoomType,
    WallType,
)
from src.schema.input_models import ReviewElementCorrection
from src.schema.provenance import ProvenanceRecord
from src.utils.completeness_scorer import HUMAN_REVIEW_THRESHOLD


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------


def _ml_provenance(detector: DetectorSource, run_id: str = "run-1") -> ProvenanceRecord:
    return ProvenanceRecord(
        detector_source=detector,
        run_id=run_id,
        confidence_from_model=0.4,
    )


def _with_low_confidence_elements(bg: BuildingGraph) -> BuildingGraph:
    """Mutate fixture walls/rooms/columns to carry low confidence."""

    bg.walls[0] = bg.walls[0].model_copy(
        update={
            "confidence": 0.35,
            "provenance": _ml_provenance(DetectorSource.CUBICASA_HG),
        }
    )
    bg.rooms[0] = bg.rooms[0].model_copy(
        update={
            "confidence": 0.45,
            "provenance": _ml_provenance(DetectorSource.VLM_GAP_FILL),
        }
    )
    bg.column_candidates[0] = bg.column_candidates[0].model_copy(
        update={
            "confidence": 0.20,
            "provenance": _ml_provenance(DetectorSource.YOLO_SEG),
        }
    )
    return bg


def _with_opening(bg: BuildingGraph) -> BuildingGraph:
    bg.openings = [
        Opening(
            id="opening-1",
            type=OpeningType.DOOR,
            wall_id=bg.walls[0].id,
            position_mm=1000.0,
            width_mm=900.0,
            confidence=0.3,
            provenance=_ml_provenance(DetectorSource.SYMBOL_DETECTOR),
        )
    ]
    return bg


def _with_core(bg: BuildingGraph) -> BuildingGraph:
    bg.cores = [
        Core(
            id="core-1",
            type=CoreType.ELEVATOR_STAIR,
            polygon=[[0, 0], [2000, 0], [2000, 2000], [0, 2000]],
            contains_elevator=True,
            contains_stairs=True,
            confidence=0.2,
            provenance=_ml_provenance(DetectorSource.CUBICASA_HG),
        )
    ]
    return bg


def _with_assumptions(bg: BuildingGraph) -> BuildingGraph:
    bg.metadata.assumption_register = [
        AssumptionRecord.quick(
            id="policy.overrideable.a",
            name="Overrideable A",
            value=100,
            unit="mm",
            source="test",
            rationale="low-conf default",
            confidence=0.4,
            overrideable=True,
        ),
        AssumptionRecord.quick(
            id="policy.overrideable.b",
            name="Overrideable B",
            value=200,
            unit="mm",
            source="test",
            rationale="medium-conf default",
            confidence=0.9,
            overrideable=True,
        ),
        AssumptionRecord.quick(
            id="policy.locked",
            name="Locked marker",
            value="STRUCTURED_FORM",
            source="test",
            rationale="channel marker",
            confidence=1.0,
            overrideable=False,
        ),
    ]
    return bg


def _with_completeness(bg: BuildingGraph, overall: float) -> BuildingGraph:
    bg.metadata.completeness = CompletenessScore(
        overall=overall,
        geometry=overall,
        semantics=overall,
        detector_coverage=overall,
        missing_subsystems=["SYMBOL_DETECTOR"] if overall < 0.5 else [],
    )
    if overall < HUMAN_REVIEW_THRESHOLD:
        bg.metadata.warnings.append(
            "requires_human_review: overall completeness below 0.5"
        )
    return bg


# ---------------------------------------------------------------------------
# build_review_snapshot
# ---------------------------------------------------------------------------


def test_snapshot_with_missing_graph_returns_empty(
) -> None:
    snap = build_review_snapshot(job_id="j-1", status="processing", bg=None)
    assert snap.job_id == "j-1"
    assert snap.status == "processing"
    assert snap.review_required is False
    assert snap.completeness is None
    assert snap.low_confidence_elements == []
    assert snap.overrideable_assumptions == []


def test_snapshot_buckets_low_confidence_elements_by_kind(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_low_confidence_elements(sample_building_graph)
    bg = _with_opening(bg)
    bg = _with_core(bg)

    snap = build_review_snapshot(job_id="j-2", status="completed", bg=bg)

    kinds = {e.kind for e in snap.low_confidence_elements}
    assert {"wall", "room", "opening", "column", "core"}.issubset(kinds)

    # All surfaced elements must actually be below the threshold.
    assert all(
        e.confidence < LOW_CONFIDENCE_THRESHOLD
        for e in snap.low_confidence_elements
    )

    # Elements with confidence >= threshold stay silent.
    ids = {(e.kind, e.id) for e in snap.low_confidence_elements}
    assert ("wall", sample_building_graph.walls[1].id) not in ids
    # The second column candidate is at 0.9 — shouldn't show up.
    assert ("column", "1") not in ids


def test_snapshot_preserves_detector_source_on_surfaced_elements(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_low_confidence_elements(sample_building_graph)
    snap = build_review_snapshot(job_id="j-3", status="completed", bg=bg)

    wall_entry = next(e for e in snap.low_confidence_elements if e.kind == "wall")
    assert wall_entry.detector_source == DetectorSource.CUBICASA_HG.value
    column_entry = next(e for e in snap.low_confidence_elements if e.kind == "column")
    assert column_entry.detector_source == DetectorSource.YOLO_SEG.value


def test_snapshot_sorts_overrideable_assumptions_lowest_first(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_assumptions(sample_building_graph)

    snap = build_review_snapshot(job_id="j-4", status="completed", bg=bg)

    ids = [a.id for a in snap.overrideable_assumptions]
    # Non-overrideable entry must be filtered out.
    assert "policy.locked" not in ids
    # Lowest-confidence first.
    assert ids == ["policy.overrideable.a", "policy.overrideable.b"]
    confidences = [a.confidence for a in snap.overrideable_assumptions]
    assert confidences == sorted(confidences)


def test_snapshot_flags_review_required_when_completeness_below_threshold(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_completeness(sample_building_graph, overall=0.3)
    snap = build_review_snapshot(job_id="j-5", status="completed", bg=bg)
    assert snap.review_required is True
    assert snap.completeness is not None
    assert snap.completeness.overall == pytest.approx(0.3)


def test_snapshot_does_not_flag_review_when_completeness_is_high(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_completeness(sample_building_graph, overall=0.9)
    snap = build_review_snapshot(job_id="j-6", status="completed", bg=bg)
    assert snap.review_required is False
    assert not any(
        w.startswith("requires_human_review:") for w in snap.warnings
    )


def test_snapshot_flags_review_when_marker_warning_present_without_score(
    sample_building_graph: BuildingGraph,
) -> None:
    """The marker warning alone is enough — even if the completeness
    field is stripped (e.g. on a hydrated legacy graph), a reviewer
    should still see the gate."""

    sample_building_graph.metadata.completeness = None
    sample_building_graph.metadata.warnings.append(
        "requires_human_review: overall completeness below 0.5"
    )
    snap = build_review_snapshot(
        job_id="j-7", status="completed", bg=sample_building_graph
    )
    assert snap.review_required is True


def test_snapshot_flags_review_on_degraded_placeholder_warning(
    sample_building_graph: BuildingGraph,
) -> None:
    """The Channel-C degraded-placeholder marker must trip the gate even
    when the scalar completeness happens to land above the threshold.

    A degraded graph synthesises a story and a fallback room to stay
    schema-valid; those can inflate overall completeness above 0.5 while
    walls / openings / columns are all zero.  The explicit
    ``degraded_placeholder_graph_emitted`` warning is the unambiguous
    signal a reviewer must still see the job.
    """

    bg = _with_completeness(sample_building_graph, overall=0.6)
    bg.metadata.warnings.append("degraded_placeholder_graph_emitted")
    snap = build_review_snapshot(job_id="j-8", status="completed", bg=bg)
    assert snap.review_required is True


# ---------------------------------------------------------------------------
# apply_corrections
# ---------------------------------------------------------------------------


def test_apply_wall_correction_stamps_user_override_and_clamps_confidence(
    sample_building_graph: BuildingGraph,
) -> None:
    bg = _with_low_confidence_elements(sample_building_graph)
    original = bg.walls[0]

    applied = apply_corrections(
        bg,
        [
            ReviewElementCorrection(
                target="wall",
                id=original.id,
                fields={"type": WallType.STRUCTURAL.value, "thickness_mm": 250.0},
            )
        ],
        run_id="run-7",
        reviewer="jdoe",
    )
    assert applied == [f"wall:{original.id}"]

    updated = bg.walls[0]
    assert updated.id == original.id
    assert updated.type == WallType.STRUCTURAL
    assert updated.thickness_mm == 250.0
    assert updated.confidence == 1.0
    assert updated.provenance is not None
    assert updated.provenance.detector_source == DetectorSource.USER_OVERRIDE
    assert updated.provenance.confidence_from_model == 1.0
    assert "jdoe" in (updated.provenance.notes or "")
    # Prior detector is preserved in the notes for auditability.
    assert DetectorSource.CUBICASA_HG.value in (updated.provenance.notes or "")


def test_apply_room_correction_can_relabel_and_retype(
    sample_building_graph: BuildingGraph,
) -> None:
    room_id = sample_building_graph.rooms[0].id

    apply_corrections(
        sample_building_graph,
        [
            ReviewElementCorrection(
                target="room",
                id=room_id,
                fields={"label": "Reviewer Lobby", "type": RoomType.LOBBY.value},
            )
        ],
        run_id="run-8",
    )
    room = sample_building_graph.rooms[0]
    assert room.label == "Reviewer Lobby"
    assert room.type == RoomType.LOBBY
    assert room.confidence == 1.0


def test_apply_column_correction_uses_index_id(
    sample_building_graph: BuildingGraph,
) -> None:
    apply_corrections(
        sample_building_graph,
        [
            ReviewElementCorrection(
                target="column",
                id="1",
                fields={"is_required": True, "notes": "Fixed by reviewer"},
            )
        ],
        run_id="run-9",
        reviewer="eng-01",
    )
    col = sample_building_graph.column_candidates[1]
    assert col.is_required is True
    assert col.notes == "Fixed by reviewer"
    assert col.confidence == 1.0
    assert col.provenance is not None
    assert col.provenance.detector_source == DetectorSource.USER_OVERRIDE


def test_apply_correction_rejects_unknown_target(
    sample_building_graph: BuildingGraph,
) -> None:
    with pytest.raises(ReviewCorrectionError, match="Unknown correction target"):
        apply_corrections(
            sample_building_graph,
            [
                # Pydantic's Literal validation would catch this on the
                # wire; call the service with a bypass dict to exercise
                # the service-side guard.
                ReviewElementCorrection.model_construct(
                    target="beam", id="x", fields={"length_mm": 1},
                )
            ],
            run_id="run-10",
        )


def test_apply_correction_rejects_unknown_field(
    sample_building_graph: BuildingGraph,
) -> None:
    with pytest.raises(ReviewCorrectionError, match="Unknown or non-editable"):
        apply_corrections(
            sample_building_graph,
            [
                ReviewElementCorrection(
                    target="wall",
                    id=sample_building_graph.walls[0].id,
                    fields={"confidence": 0.1},  # service-managed
                )
            ],
            run_id="run-11",
        )


def test_apply_correction_raises_lookup_error_on_missing_id(
    sample_building_graph: BuildingGraph,
) -> None:
    with pytest.raises(LookupError):
        apply_corrections(
            sample_building_graph,
            [
                ReviewElementCorrection(
                    target="wall",
                    id="wall-does-not-exist",
                    fields={"thickness_mm": 300},
                )
            ],
            run_id="run-12",
        )


def test_apply_correction_rolls_forward_then_fails(
    sample_building_graph: BuildingGraph,
) -> None:
    """First correction lands; the second raises.  The graph keeps the
    first edit — same semantics as the existing override endpoint."""

    good_id = sample_building_graph.walls[0].id
    with pytest.raises(LookupError):
        apply_corrections(
            sample_building_graph,
            [
                ReviewElementCorrection(
                    target="wall",
                    id=good_id,
                    fields={"thickness_mm": 400},
                ),
                ReviewElementCorrection(
                    target="room",
                    id="nope",
                    fields={"label": "X"},
                ),
            ],
            run_id="run-13",
        )
    assert sample_building_graph.walls[0].thickness_mm == 400
    assert sample_building_graph.walls[0].confidence == 1.0
