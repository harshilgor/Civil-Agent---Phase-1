"""Tests for the Step 2 Building Graph extensions: shared assumptions,
provenance, per-element confidence, completeness scoring, schema versioning,
and inferred building type.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema import (
    SCHEMA_VERSION,
    AssumptionRecord,
    BuildingGraph,
    BuildingMetadata,
    BuildingType,
    CompletenessScore,
    ConfidenceLevel,
    ConfidenceScores,
    Core,
    CoreType,
    DetectorSource,
    InputSource,
    Opening,
    OpeningType,
    ProvenanceRecord,
    Room,
    RoomType,
    WallSegment,
    WallType,
    confidence_to_level,
)


# ── Shared enums & helpers ────────────────────────────────────────────────


class TestSharedEnums:
    def test_building_type_values(self):
        assert BuildingType.RESIDENTIAL.value == "RESIDENTIAL"
        assert BuildingType.UNKNOWN.value == "UNKNOWN"
        assert len(BuildingType) == 6

    def test_detector_source_includes_perception_and_user(self):
        names = {member.value for member in DetectorSource}
        assert "CUBICASA_HG" in names
        assert "SMP_UNET" in names
        assert "YOLO_SEG" in names
        assert "VLM_GAP_FILL" in names
        assert "USER_OVERRIDE" in names
        assert "STRUCTURED_FORM" in names

    def test_confidence_level_buckets(self):
        assert confidence_to_level(0.95) is ConfidenceLevel.HIGH
        assert confidence_to_level(0.85) is ConfidenceLevel.HIGH
        assert confidence_to_level(0.7) is ConfidenceLevel.MEDIUM
        assert confidence_to_level(0.6) is ConfidenceLevel.MEDIUM
        assert confidence_to_level(0.59) is ConfidenceLevel.LOW
        assert confidence_to_level(0.0) is ConfidenceLevel.LOW


# ── AssumptionRecord (shared) ─────────────────────────────────────────────


class TestAssumptionRecord:
    def test_quick_factory_derives_level(self):
        rec = AssumptionRecord.quick(
            id="wall_thickness_default",
            name="Default wall thickness",
            value=200.0,
            unit="mm",
            source="Phase 1 / heuristic",
            rationale="No thickness annotated; falls back to 200 mm partition default.",
            confidence=0.7,
            affects_modules=["phase1.wall_reconstruction"],
        )
        assert rec.confidence_level is ConfidenceLevel.MEDIUM
        assert rec.effective_value == 200.0
        assert rec.was_overridden is False
        assert "phase1.wall_reconstruction" in rec.affects_modules

    def test_override_replaces_effective_value(self):
        rec = AssumptionRecord.quick(
            id="wind_exposure",
            name="Wind exposure category",
            value="C",
            source="ASCE 7-22 §26.7",
            rationale="Suburban surroundings inferred from VLM scene tag.",
            confidence=0.8,
        )
        overridden = rec.model_copy(
            update={
                "was_overridden": True,
                "override_value": "B",
                "override_source": "user_review",
            }
        )
        assert overridden.effective_value == "B"

    def test_phase3_re_export_is_same_class(self):
        from src.phase3.models.assumptions import AssumptionRecord as Phase3Record

        assert Phase3Record is AssumptionRecord


# ── ProvenanceRecord ──────────────────────────────────────────────────────


class TestProvenanceRecord:
    def test_minimal_record(self):
        prov = ProvenanceRecord(detector_source=DetectorSource.STRUCTURED_FORM)
        assert prov.detector_source is DetectorSource.STRUCTURED_FORM
        assert prov.model_id is None
        assert prov.created_at is not None

    def test_full_record_round_trip(self):
        prov = ProvenanceRecord(
            detector_source=DetectorSource.CUBICASA_HG,
            model_id="cubicasa_hg_v1",
            model_version="1.0.0",
            weights_manifest_hash="a" * 64,
            run_id="job-abc-123",
            confidence_from_model=0.92,
            notes="Merged with adjacent segment after orthogonal snap.",
        )
        restored = ProvenanceRecord.model_validate_json(prov.model_dump_json())
        assert restored.model_id == "cubicasa_hg_v1"
        assert restored.confidence_from_model == 0.92

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="confidence_from_model"):
            ProvenanceRecord(
                detector_source=DetectorSource.YOLO_SEG,
                confidence_from_model=1.2,
            )


# ── Per-element confidence + provenance ───────────────────────────────────


class TestPerElementConfidence:
    def test_wall_default_confidence_is_one(self):
        w = WallSegment(
            id="w1",
            type=WallType.STRUCTURAL,
            start=[0, 0],
            end=[8000, 0],
            thickness_mm=200,
            stories=["s0"],
        )
        assert w.confidence == 1.0
        assert w.provenance is None

    def test_wall_with_provenance_and_confidence(self):
        prov = ProvenanceRecord(
            detector_source=DetectorSource.YOLO_SEG,
            confidence_from_model=0.81,
        )
        w = WallSegment(
            id="w1",
            type=WallType.PARTITION,
            start=[0, 0],
            end=[4000, 0],
            thickness_mm=120,
            stories=["s0"],
            confidence=0.81,
            provenance=prov,
        )
        assert w.confidence == 0.81
        assert w.provenance.detector_source is DetectorSource.YOLO_SEG

    def test_room_confidence_out_of_range(self):
        with pytest.raises(ValidationError, match="confidence"):
            Room(
                id="r1",
                label="X",
                type=RoomType.UNDEFINED,
                polygon=[[0, 0], [1000, 0], [1000, 1000]],
                area_m2=1.0,
                story="s0",
                confidence=1.5,
            )

    def test_opening_carries_provenance(self):
        prov = ProvenanceRecord(
            detector_source=DetectorSource.SYMBOL_DETECTOR,
            model_id="symbol_yolov8s",
            confidence_from_model=0.74,
        )
        o = Opening(
            id="o1",
            type=OpeningType.DOOR,
            wall_id="w1",
            position_mm=2000,
            width_mm=900,
            confidence=0.74,
            provenance=prov,
        )
        assert o.provenance.model_id == "symbol_yolov8s"

    def test_core_confidence_default(self):
        c = Core(
            id="c1",
            type=CoreType.ELEVATOR_STAIR,
            polygon=[[0, 0], [3000, 0], [3000, 5000]],
        )
        assert c.confidence == 1.0


# ── CompletenessScore ─────────────────────────────────────────────────────


class TestCompletenessScore:
    def test_valid(self):
        cs = CompletenessScore(
            overall=0.78,
            geometry=0.9,
            semantics=0.7,
            detector_coverage=0.6,
            missing_subsystems=["yolo_seg"],
        )
        assert cs.overall == 0.78
        assert "yolo_seg" in cs.missing_subsystems

    def test_overall_out_of_range(self):
        with pytest.raises(ValidationError, match="overall"):
            CompletenessScore(
                overall=1.1,
                geometry=0.5,
                semantics=0.5,
                detector_coverage=0.5,
            )

    def test_required_fields_enforced(self):
        with pytest.raises(ValidationError):
            CompletenessScore(overall=0.5)  # type: ignore[call-arg]


# ── ConfidenceScores subsystem additions ──────────────────────────────────


class TestConfidenceScoresAdditions:
    def test_new_subsystem_fields(self):
        cs = ConfidenceScores(
            wall_detection=0.9,
            opening_detection=0.7,
            column_inference=0.8,
            overall=0.8,
        )
        assert cs.opening_detection == 0.7
        assert cs.column_inference == 0.8


# ── BuildingMetadata upgrades ─────────────────────────────────────────────


class TestBuildingMetadataUpgrades:
    def test_metadata_with_register_and_inferred_type(self):
        rec = AssumptionRecord.quick(
            id="ground_floor_height",
            name="Ground floor height fallback",
            value=4500.0,
            unit="mm",
            source="Phase 1 / structured-form default",
            rationale="ground_floor_height_mm not supplied; using 4.5 m.",
            confidence=0.9,
        )
        md = BuildingMetadata(
            input_source=InputSource.STRUCTURED_FORM,
            inferred_building_type=BuildingType.COMMERCIAL,
            assumption_register=[rec],
            job_id="job-xyz-001",
            completeness=CompletenessScore(
                overall=0.95,
                geometry=1.0,
                semantics=0.9,
                detector_coverage=0.9,
            ),
        )
        assert md.inferred_building_type is BuildingType.COMMERCIAL
        assert md.job_id == "job-xyz-001"
        assert md.assumption_register[0].id == "ground_floor_height"
        assert md.completeness.overall == 0.95
        # Legacy field still present and defaults to []
        assert md.assumptions_made == []


# ── BuildingGraph schema_version ──────────────────────────────────────────


class TestBuildingGraphSchemaVersion:
    def test_schema_version_default(self, sample_building_graph):
        assert sample_building_graph.schema_version == SCHEMA_VERSION

    def test_schema_version_round_trip(self, sample_building_graph):
        restored = BuildingGraph.model_validate_json(
            sample_building_graph.model_dump_json()
        )
        assert restored.schema_version == SCHEMA_VERSION

    def test_schema_version_format(self):
        parts = SCHEMA_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)
