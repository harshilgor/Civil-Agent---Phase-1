"""Step-10 end-to-end integration tests for :class:`ImageGraphBuilder`.

These tests drive the full Channel-C pipeline (Stages 1-10) against
a synthetic floor-plan image with every ML component replaced by a
deterministic fake.  That means:

*   No torch / ultralytics / anthropic is imported during the run.
*   The "segmentation mask" is a hand-drawn ``np.ndarray`` with four
    wall strokes forming a rectangular room.
*   The "symbol detections" are two pre-set bounding boxes.
*   The VLM classifier always returns a fixed
    :class:`ClassificationResult`.

What's exercised for real:

*   :class:`Vectorizer` turning the raster mask into mm-scale segments.
*   :class:`GeometryPostProcessor` cleaning the geometry and inferring
    rooms / grid / columns / cores.
*   :meth:`ImageGraphBuilder._symbols_to_openings` snapping YOLO bboxes
    onto the vectorised walls.
*   The assumption-register stitcher, confidence scorer, and
    :func:`annotate_with_completeness` gate.

The graph that falls out the other end must be schema-valid, carry
the VLM classification on its metadata, and have non-trivial wall /
room / opening populations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pytest
from PIL import Image

from src.core.image_graph_builder import ImageGraphBuildResult, ImageGraphBuilder
from src.cv.building_type_classifier import (
    BuildingTypeClassifier,
    ClassificationResult,
)
from src.cv.detector_adapters import SymbolDetection
from src.cv.ml_engine import (
    MLEngine,
    SymbolDetectionResult,
    WallSegmentationResult,
)
from src.schema.enums import (
    BuildingType,
    DetectorSource,
    InputSource,
    OccupancyType,
    OpeningType,
)
from src.schema.provenance import ProvenanceRecord


# ---------------------------------------------------------------------------
# Fakes — injected via the ImageGraphBuilder constructor seams.
# ---------------------------------------------------------------------------


class _FakeClassifier(BuildingTypeClassifier):
    """Classifier that always returns a fixed result — no API calls."""

    def __init__(self, result: ClassificationResult) -> None:
        # Deliberately skip super().__init__ so we never touch the
        # anthropic SDK.  The builder only calls ``.classify(bytes)``.
        self._result = result

    def classify(self, image_bytes: bytes) -> ClassificationResult:  # type: ignore[override]
        return self._result


@dataclass
class _FakeMLEngine:
    """Stand-in for :class:`MLEngine` driven by pre-baked outputs.

    The real ``MLEngine`` reads its three manifest slots, builds
    adapters, and calls them per image.  For Step-10 integration
    testing we need none of that — we hand the builder a crisp mask
    and a deterministic bbox list so the downstream stages (vectorise,
    post-process, assemble) are the only things actually exercised.
    """

    wall_mask: np.ndarray
    wall_confidence: float
    symbol_detections: list[SymbolDetection] = field(default_factory=list)
    primary_slot_name: Optional[str] = "wall_segmenter_residential"
    fallback_slot_name: Optional[str] = "wall_fallback_yoloseg"
    symbol_slot_name: Optional[str] = "symbol_detector_universal"
    used_fallback: bool = False
    wall_notes: list[str] = field(default_factory=list)
    symbol_enabled: bool = True

    # -- MLEngine-shaped surface ---------------------------------------

    @property
    def primary_slot(self) -> Optional[str]:
        return self.primary_slot_name

    @property
    def fallback_slot(self) -> Optional[str]:
        return self.fallback_slot_name

    @property
    def symbol_slot(self) -> Optional[str]:
        return self.symbol_slot_name

    def segment_walls(self, image: np.ndarray) -> WallSegmentationResult:
        prov = ProvenanceRecord(
            detector_source=DetectorSource.CUBICASA_HG,
            model_id="fake-cubicasa",
            model_version="test",
            run_id="test-run",
            confidence_from_model=self.wall_confidence,
        )
        return WallSegmentationResult(
            mask=self.wall_mask,
            element_masks={},
            confidence=self.wall_confidence,
            provenance=prov,
            used_fallback=self.used_fallback,
            primary_slot=self.primary_slot_name,
            fallback_slot=self.fallback_slot_name,
            notes=list(self.wall_notes),
        )

    def detect_symbols(self, image: np.ndarray) -> SymbolDetectionResult:
        if not self.symbol_enabled:
            return SymbolDetectionResult(
                detections=[],
                provenance=None,
                enabled=False,
                slot=None,
                notes=["symbol detector disabled by test fake"],
            )
        prov = ProvenanceRecord(
            detector_source=DetectorSource.SYMBOL_DETECTOR,
            model_id="fake-yolov8",
            model_version="test",
            run_id="test-run",
            confidence_from_model=1.0,
        )
        return SymbolDetectionResult(
            detections=list(self.symbol_detections),
            provenance=prov,
            enabled=True,
            slot=self.symbol_slot_name,
            notes=[],
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_png(path: Path, size: tuple[int, int] = (400, 300)) -> Path:
    img = Image.new("RGB", size, color=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


def _rectangular_wall_mask(
    shape: tuple[int, int] = (400, 500),
    inset: int = 40,
    thickness: int = 8,
) -> np.ndarray:
    """Draw a thick-walled rectangle into a 2-D uint8 mask.

    The mask is laid out so the vectoriser has four clean lines
    (one per side) with no extraneous Hough responses.  Returns
    values 0 / 255 — matches the contract
    :class:`WallSegmentationOutput.wall_mask` documents.
    """

    h, w = shape
    mask = np.zeros((h, w), dtype=np.uint8)
    y0, y1 = inset, h - inset
    x0, x1 = inset, w - inset
    mask[y0 : y0 + thickness, x0:x1] = 255  # top
    mask[y1 - thickness : y1, x0:x1] = 255  # bottom
    mask[y0:y1, x0 : x0 + thickness] = 255  # left
    mask[y0:y1, x1 - thickness : x1] = 255  # right
    return mask


@pytest.fixture()
def png_path(tmp_path: Path) -> Path:
    return _make_png(tmp_path / "plan.png")


@pytest.fixture()
def fake_classifier_residential() -> _FakeClassifier:
    return _FakeClassifier(
        ClassificationResult(
            building_type=BuildingType.RESIDENTIAL,
            confidence=0.9,
            rationale="synthetic_fixture",
            model_id="fake-claude",
            raw_response=None,
            is_fallback=False,
        )
    )


@pytest.fixture()
def fake_classifier_fallback() -> _FakeClassifier:
    return _FakeClassifier(
        ClassificationResult(
            building_type=BuildingType.UNKNOWN,
            confidence=0.0,
            rationale="vlm unavailable",
            model_id="fake-claude",
            raw_response=None,
            is_fallback=True,
        )
    )


def _make_builder(
    classifier: _FakeClassifier,
    ml_engine: _FakeMLEngine,
) -> ImageGraphBuilder:
    return ImageGraphBuilder(
        classifier=classifier,
        ml_engine_factory=lambda bt, run_id: ml_engine,
    )


# ---------------------------------------------------------------------------
# Happy path — mask → walls → graph
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_synthetic_mask_yields_real_wall_graph(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """The full pipeline over a rectangular-room mask must emit
        non-zero walls, a grid, and land the VLM classification on
        the metadata."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(),
            wall_confidence=0.82,
            symbol_detections=[],
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-happy")

        assert isinstance(result, ImageGraphBuildResult)
        assert result.degraded is False
        assert result.wall_count >= 4  # four sides of the room
        assert result.selected_slot == "wall_segmenter_residential"
        assert result.used_fallback_segmenter is False

        graph = result.graph
        assert graph.metadata.input_source == InputSource.FLOOR_PLAN_IMAGE
        assert graph.metadata.inferred_building_type == BuildingType.RESIDENTIAL
        assert len(graph.walls) >= 4
        assert graph.facade.perimeter_length_mm > 0
        assert len(graph.stories) == 1

        # Completeness annotation must have run.
        assert graph.metadata.completeness is not None
        assert 0.0 <= graph.metadata.completeness.overall <= 1.0

    def test_walls_carry_ml_provenance(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """Every wall on the happy path must carry a CUBICASA_HG
        provenance stamp coming from the fake ML engine — the
        vectoriser does not invent walls so this is a round-trip check."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(), wall_confidence=0.75
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-prov")

        assert result.graph.walls, "expected some walls"
        for wall in result.graph.walls:
            assert wall.provenance is not None
            assert wall.provenance.detector_source == DetectorSource.CUBICASA_HG
            assert wall.provenance.model_id == "fake-cubicasa"

    def test_symbols_snap_to_nearest_wall(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """A door bbox placed near the top wall must emit an Opening
        bound to one of the walls, with OpeningType.DOOR."""

        mask = _rectangular_wall_mask(shape=(400, 500))
        # Place a "door" bbox centred on the top wall at (250 px, 40 px).
        door_bbox = (235, 30, 265, 50)
        engine = _FakeMLEngine(
            wall_mask=mask,
            wall_confidence=0.8,
            symbol_detections=[
                SymbolDetection(class_name="door", bbox=door_bbox, confidence=0.9)
            ],
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-symbols")

        assert result.symbol_count == 1
        assert len(result.graph.openings) == 1
        op = result.graph.openings[0]
        assert op.type == OpeningType.DOOR
        assert op.wall_id in {w.id for w in result.graph.walls}
        assert op.confidence == pytest.approx(0.9, abs=0.01)

    def test_vlm_fallback_preserves_occupancy_default(
        self, png_path: Path, fake_classifier_fallback: _FakeClassifier
    ):
        """When the VLM is unavailable the pipeline must keep a sensible
        occupancy-derived :class:`BuildingType` on the metadata — not
        leak ``UNKNOWN`` into downstream manifest selection."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(), wall_confidence=0.8
        )
        builder = _make_builder(fake_classifier_fallback, engine)

        result = builder.build(
            png_path,
            run_id="test-fallback",
            occupancy_type=OccupancyType.RESIDENTIAL,
        )
        # RESIDENTIAL occupancy → RESIDENTIAL building type via fallback.
        assert (
            result.graph.metadata.inferred_building_type
            == BuildingType.RESIDENTIAL
        )
        assert result.classification.is_fallback is True

    def test_assumption_register_surfaces_geometry_policy(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """The geometry post-processor emits overrideable policy
        assumptions (orthogonality, snap radius, junction radius).  On
        the end-to-end path they must reach the final graph — they are
        the reviewer's hook for disabling Step-9 behaviour on
        non-orthogonal buildings."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(), wall_confidence=0.8
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-policy")

        ids = {a.id for a in result.graph.metadata.assumption_register}
        assert "geometry.orthogonality_policy" in ids
        assert "geometry.snap_weld_radius" in ids
        assert "geometry.corner_junction_radius" in ids

        ortho = next(
            a for a in result.graph.metadata.assumption_register
            if a.id == "geometry.orthogonality_policy"
        )
        assert ortho.overrideable is True
        assert ortho.unit == "deg"

    def test_scale_assumption_records_fallback(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """No caller-supplied scale → vectoriser infers → the scale
        assumption must surface as overrideable with low confidence so
        a reviewer can correct the mm-per-pixel."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(), wall_confidence=0.8
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-scale")

        scale = next(
            a for a in result.graph.metadata.assumption_register
            if a.id == "channel_c_scale_factor"
        )
        assert scale.unit == "mm/px"
        assert scale.overrideable is True
        assert scale.confidence <= 0.5  # inferred -> low confidence

    def test_used_fallback_segmenter_flag_propagates(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """When the ML engine reports ``used_fallback=True`` the
        builder must (1) set ``used_fallback_segmenter=True`` on the
        result, and (2) surface a warning on the graph so the reviewer
        notices the primary didn't carry the run."""

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(),
            wall_confidence=0.55,
            used_fallback=True,
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-fallback-flag")
        assert result.used_fallback_segmenter is True
        assert any(
            w.startswith("wall_segmentation_used_fallback_slot")
            for w in result.graph.metadata.warnings
        )


# ---------------------------------------------------------------------------
# Degraded path — empty mask
# ---------------------------------------------------------------------------


class TestDegradedPath:
    def test_empty_mask_emits_schema_valid_placeholder(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """Empty segmentation mask → zero walls → degraded placeholder
        graph.  Must still be schema-valid so the review UI can
        render it, and the ``channel_c_degraded_placeholder``
        assumption must fire."""

        engine = _FakeMLEngine(
            wall_mask=np.zeros((200, 300), dtype=np.uint8),
            wall_confidence=0.0,
        )
        builder = _make_builder(fake_classifier_residential, engine)

        result = builder.build(png_path, run_id="test-degraded")

        assert result.degraded is True
        assert result.wall_count == 0
        graph = result.graph
        assert graph.walls == []
        assert graph.metadata.completeness is not None
        assert graph.metadata.completeness.overall == pytest.approx(
            graph.metadata.confidence_scores.overall, abs=0.001
        )

        ids = {a.id for a in graph.metadata.assumption_register}
        assert "channel_c_degraded_placeholder" in ids
        assert "image_pipeline_produced_no_walls" in graph.metadata.warnings

    def test_degraded_graph_preserves_classification(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """Even with zero walls, the VLM classification must still
        land on the graph — the reviewer needs to see what Stage 2
        inferred, independent of the ML engine collapsing."""

        engine = _FakeMLEngine(
            wall_mask=np.zeros((100, 100), dtype=np.uint8),
            wall_confidence=0.0,
        )
        builder = _make_builder(fake_classifier_residential, engine)
        result = builder.build(png_path, run_id="test-degraded-cls")

        assert (
            result.graph.metadata.inferred_building_type == BuildingType.RESIDENTIAL
        )


# ---------------------------------------------------------------------------
# Worker integration — _run_image_pipeline with injected builder
# ---------------------------------------------------------------------------


class TestWorkerIntegration:
    def test_run_image_pipeline_consumes_injected_builder(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """The worker task takes an optional ``builder`` kwarg so
        tests can drive the happy path without real ML weights."""

        from src.worker.tasks import _run_image_pipeline

        engine = _FakeMLEngine(
            wall_mask=_rectangular_wall_mask(), wall_confidence=0.82
        )
        builder = _make_builder(fake_classifier_residential, engine)

        payload = _run_image_pipeline(
            "job-integration", str(png_path), builder=builder
        )
        assert payload["status"] == "ok"
        assert payload["channel"] == "image"
        assert payload["stub"] is False
        assert payload["stage_completed"] == "stage_10_building_graph"
        assert payload["wall_count"] >= 4
        assert payload["classification"]["building_type"] == "RESIDENTIAL"
        assert payload["selected_slot"] == "wall_segmenter_residential"

    def test_run_image_pipeline_degraded_payload_shape(
        self, png_path: Path, fake_classifier_residential: _FakeClassifier
    ):
        """Worker payload for a degraded graph must carry
        ``stub=True`` and ``stage_completed=stage_10_degraded_placeholder``
        so the endpoint can flag it to the reviewer."""

        from src.worker.tasks import _run_image_pipeline

        engine = _FakeMLEngine(
            wall_mask=np.zeros((120, 160), dtype=np.uint8),
            wall_confidence=0.0,
        )
        builder = _make_builder(fake_classifier_residential, engine)

        payload = _run_image_pipeline(
            "job-integration-degraded", str(png_path), builder=builder
        )
        assert payload["stub"] is True
        assert payload["stage_completed"] == "stage_10_degraded_placeholder"
        assert payload["wall_count"] == 0
