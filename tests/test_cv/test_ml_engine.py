"""Integration tests for :class:`src.cv.ml_engine.MLEngine`.

These exercise the dispatch + fallback + symbol-detector logic end-to-end
without touching real model weights.  Every wall segmenter is a fake
adapter that returns hand-crafted :class:`WallSegmentationOutput`
instances; the symbol detector is a fake that returns hand-crafted
:class:`SymbolDetection` lists.  The goal is to prove:

1. High-confidence primary → result carries primary provenance, no
   fallback engaged.
2. Low-confidence primary → fallback engaged; result provenance
   switches to fallback's; notes record why.
3. Primary raises → fallback engaged; notes record the exception.
4. No primary resolved + fallback resolved → fallback used from the
   start with an explanatory note.
5. Neither resolved → empty mask with a ``VLM_GAP_FILL`` stub provenance
   so downstream consumers can tell ``model_id`` == ``ml_engine_stub``.
6. Symbol detector present → detections returned with provenance; notes
   empty.
7. Symbol detector absent → ``enabled=False``, empty detections.
8. Symbol detector raises → ``enabled=True``, empty detections, notes
   record the exception.
9. :meth:`MLEngine.from_loader` selects the right manifest slot for the
   given :class:`BuildingType` and stamps the manifest hash on the
   provenance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.weights.backends import LocalWeightsBackend
from backend.weights.loader import WeightsLoader
from backend.weights.manifest import WeightsManifest
from src.cv.detector_adapters import (
    SymbolDetection,
    WallSegmentationOutput,
)
from src.cv.ml_engine import (
    DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD,
    KIND_SYMBOL_DETECTOR,
    KIND_WALL_FALLBACK,
    KIND_WALL_PRIMARY,
    MLEngine,
    ResolvedDetector,
    SymbolDetectionResult,
    WallSegmentationResult,
)
from src.schema.enums import BuildingType, DetectorSource
from src.schema.provenance import ProvenanceRecord


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeWallAdapter:
    """Configurable fake wall adapter — returns a pre-baked output."""

    def __init__(
        self,
        *,
        wall_mask: np.ndarray,
        confidence: float,
        raises: Optional[Exception] = None,
    ):
        self._wall_mask = wall_mask
        self._confidence = confidence
        self._raises = raises
        self.calls: list[np.ndarray] = []

    def segment(self, image: np.ndarray) -> WallSegmentationOutput:
        self.calls.append(image)
        if self._raises is not None:
            raise self._raises
        return WallSegmentationOutput(
            wall_mask=self._wall_mask,
            element_masks={},
            confidence=self._confidence,
        )


class _FakeSymbolAdapter:
    def __init__(
        self,
        *,
        detections: list[SymbolDetection],
        raises: Optional[Exception] = None,
    ):
        self._detections = detections
        self._raises = raises
        self.calls: list[np.ndarray] = []

    def detect(self, image: np.ndarray) -> list[SymbolDetection]:
        self.calls.append(image)
        if self._raises is not None:
            raise self._raises
        return list(self._detections)


def _mk_resolved_detector(
    *,
    slot: str,
    detector_source: DetectorSource,
    model_id: str,
    adapter,
    manifest_hash: str = "f" * 64,
) -> ResolvedDetector:
    provenance = ProvenanceRecord(
        detector_source=detector_source,
        model_id=model_id,
        model_version="1.0.0",
        weights_manifest_hash=manifest_hash,
        run_id="test-run",
    )
    return ResolvedDetector(slot=slot, adapter=adapter, provenance=provenance)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def image() -> np.ndarray:
    return np.full((64, 96, 3), 255, dtype=np.uint8)


@pytest.fixture()
def wall_primary_mask() -> np.ndarray:
    m = np.zeros((64, 96), dtype=np.uint8)
    m[20:40, 20:70] = 255  # 1000 pixels
    return m


@pytest.fixture()
def wall_fallback_mask() -> np.ndarray:
    # Slightly different shape so tests can tell the two apart.
    m = np.zeros((64, 96), dtype=np.uint8)
    m[30:55, 10:85] = 255  # 1875 pixels
    return m


# ===========================================================================
# Wall segmentation — primary path
# ===========================================================================


class TestSegmentWallsPrimaryPath:
    def test_high_confidence_primary_used_without_fallback(
        self, image: np.ndarray, wall_primary_mask: np.ndarray, wall_fallback_mask: np.ndarray
    ):
        primary_adapter = _FakeWallAdapter(
            wall_mask=wall_primary_mask, confidence=0.85
        )
        fallback_adapter = _FakeWallAdapter(
            wall_mask=wall_fallback_mask, confidence=0.90
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            run_id="run-1",
            wall_primary=_mk_resolved_detector(
                slot="wall_segmenter_residential",
                detector_source=DetectorSource.CUBICASA_HG,
                model_id="cubicasa_hg_v1",
                adapter=primary_adapter,
            ),
            wall_fallback=_mk_resolved_detector(
                slot="yolo_wall_seg",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert isinstance(result, WallSegmentationResult)
        assert result.used_fallback is False
        assert result.confidence == pytest.approx(0.85)
        np.testing.assert_array_equal(result.mask, wall_primary_mask)
        assert result.provenance.detector_source == DetectorSource.CUBICASA_HG
        assert result.provenance.model_id == "cubicasa_hg_v1"
        assert result.provenance.confidence_from_model == pytest.approx(0.85)
        assert fallback_adapter.calls == []  # never called

    def test_primary_only_with_no_fallback_still_returns_primary(
        self, image: np.ndarray, wall_primary_mask: np.ndarray
    ):
        primary_adapter = _FakeWallAdapter(
            wall_mask=wall_primary_mask, confidence=0.77
        )
        engine = MLEngine(
            building_type=BuildingType.COMMERCIAL,
            wall_primary=_mk_resolved_detector(
                slot="primary",
                detector_source=DetectorSource.SMP_UNET,
                model_id="smp_unet_foo",
                adapter=primary_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is False
        assert result.provenance.model_id == "smp_unet_foo"
        assert result.fallback_slot is None
        assert result.primary_slot == "primary"


# ===========================================================================
# Wall segmentation — fallback paths
# ===========================================================================


class TestSegmentWallsFallbackEngagement:
    def test_low_confidence_primary_engages_fallback(
        self, image: np.ndarray, wall_primary_mask: np.ndarray, wall_fallback_mask: np.ndarray
    ):
        primary_adapter = _FakeWallAdapter(
            wall_mask=wall_primary_mask, confidence=0.05  # below 0.20 default
        )
        fallback_adapter = _FakeWallAdapter(
            wall_mask=wall_fallback_mask, confidence=0.75
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            wall_primary=_mk_resolved_detector(
                slot="wall_segmenter_residential",
                detector_source=DetectorSource.CUBICASA_HG,
                model_id="cubicasa_hg_v1",
                adapter=primary_adapter,
            ),
            wall_fallback=_mk_resolved_detector(
                slot="yolo_wall_seg",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is True
        assert result.provenance.detector_source == DetectorSource.YOLO_SEG
        assert result.provenance.model_id == "yolo_wall_seg"
        np.testing.assert_array_equal(result.mask, wall_fallback_mask)
        # Confidence carried over from the fallback.
        assert result.confidence == pytest.approx(0.75)
        assert result.provenance.confidence_from_model == pytest.approx(0.75)
        # Notes explain the switch.
        assert any("below threshold" in n for n in result.notes)
        assert len(primary_adapter.calls) == 1
        assert len(fallback_adapter.calls) == 1

    def test_primary_raises_engages_fallback(
        self, image: np.ndarray, wall_fallback_mask: np.ndarray
    ):
        primary_adapter = _FakeWallAdapter(
            wall_mask=np.zeros((1, 1), np.uint8),
            confidence=0.0,
            raises=RuntimeError("cuda oom"),
        )
        fallback_adapter = _FakeWallAdapter(
            wall_mask=wall_fallback_mask, confidence=0.60
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            wall_primary=_mk_resolved_detector(
                slot="primary",
                detector_source=DetectorSource.CUBICASA_HG,
                model_id="cubicasa_hg_v1",
                adapter=primary_adapter,
            ),
            wall_fallback=_mk_resolved_detector(
                slot="yolo_wall_seg",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is True
        assert any("cuda oom" in n for n in result.notes)
        assert any("primary wall segmenter raised" in n for n in result.notes)

    def test_no_primary_but_fallback_present_uses_fallback(
        self, image: np.ndarray, wall_fallback_mask: np.ndarray
    ):
        fallback_adapter = _FakeWallAdapter(
            wall_mask=wall_fallback_mask, confidence=0.50
        )
        engine = MLEngine(
            building_type=BuildingType.COMMERCIAL,
            wall_primary=None,
            wall_fallback=_mk_resolved_detector(
                slot="yolo_wall_seg",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is True
        np.testing.assert_array_equal(result.mask, wall_fallback_mask)
        assert any("no primary wall segmenter resolved" in n for n in result.notes)

    def test_primary_at_exactly_threshold_does_not_trigger_fallback(
        self, image: np.ndarray, wall_primary_mask: np.ndarray, wall_fallback_mask: np.ndarray
    ):
        """The check is ``<``, not ``<=`` — at exactly threshold the
        primary wins so the fallback isn't wasted on borderline calls."""

        threshold = DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD
        primary_adapter = _FakeWallAdapter(
            wall_mask=wall_primary_mask, confidence=threshold
        )
        fallback_adapter = _FakeWallAdapter(
            wall_mask=wall_fallback_mask, confidence=0.99
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            wall_primary=_mk_resolved_detector(
                slot="primary",
                detector_source=DetectorSource.CUBICASA_HG,
                model_id="cubicasa_hg_v1",
                adapter=primary_adapter,
            ),
            wall_fallback=_mk_resolved_detector(
                slot="yolo_wall_seg",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is False
        assert fallback_adapter.calls == []

    def test_fallback_also_raises_returns_stub(self, image: np.ndarray):
        primary_adapter = _FakeWallAdapter(
            wall_mask=np.zeros((1, 1), np.uint8),
            confidence=0.0,
            raises=RuntimeError("primary oops"),
        )
        fallback_adapter = _FakeWallAdapter(
            wall_mask=np.zeros((1, 1), np.uint8),
            confidence=0.0,
            raises=RuntimeError("fallback oops too"),
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            wall_primary=_mk_resolved_detector(
                slot="primary",
                detector_source=DetectorSource.CUBICASA_HG,
                model_id="cubicasa_hg_v1",
                adapter=primary_adapter,
            ),
            wall_fallback=_mk_resolved_detector(
                slot="fallback",
                detector_source=DetectorSource.YOLO_SEG,
                model_id="yolo_wall_seg",
                adapter=fallback_adapter,
            ),
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is False
        assert result.provenance.detector_source == DetectorSource.VLM_GAP_FILL
        assert result.provenance.model_id == "ml_engine_stub"
        assert result.mask.shape == image.shape[:2]
        assert (result.mask == 0).all()
        assert any("primary oops" in n for n in result.notes)
        assert any("fallback oops too" in n for n in result.notes)


# ===========================================================================
# Wall segmentation — no detectors available
# ===========================================================================


class TestSegmentWallsNoDetector:
    def test_returns_stub_mask_and_provenance_when_neither_resolved(
        self, image: np.ndarray
    ):
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            run_id="run-42",
            wall_primary=None,
            wall_fallback=None,
        )
        result = engine.segment_walls(image)
        assert result.used_fallback is False
        assert result.mask.shape == image.shape[:2]
        assert (result.mask == 0).all()
        assert result.confidence == 0.0
        assert result.provenance.detector_source == DetectorSource.VLM_GAP_FILL
        assert result.provenance.model_id == "ml_engine_stub"
        assert result.provenance.run_id == "run-42"
        assert any("no primary wall segmenter resolved" in n for n in result.notes)
        assert any("no wall segmenter was available" in n for n in result.notes)


# ===========================================================================
# Symbol detection
# ===========================================================================


class TestDetectSymbols:
    def test_returns_detections_with_provenance_when_enabled(
        self, image: np.ndarray
    ):
        detections = [
            SymbolDetection(class_name="door", bbox=(10, 20, 40, 60), confidence=0.8),
            SymbolDetection(class_name="window", bbox=(50, 10, 70, 30), confidence=0.6),
        ]
        symbol_adapter = _FakeSymbolAdapter(detections=detections)
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            symbol=_mk_resolved_detector(
                slot="symbol_detector",
                detector_source=DetectorSource.SYMBOL_DETECTOR,
                model_id="symbol_yolov8",
                adapter=symbol_adapter,
            ),
        )
        result = engine.detect_symbols(image)
        assert isinstance(result, SymbolDetectionResult)
        assert result.enabled is True
        assert result.slot == "symbol_detector"
        assert len(result.detections) == 2
        assert result.detections[0].class_name == "door"
        assert result.provenance is not None
        assert result.provenance.detector_source == DetectorSource.SYMBOL_DETECTOR
        assert result.notes == []

    def test_returns_empty_when_detector_disabled(self, image: np.ndarray):
        engine = MLEngine(
            building_type=BuildingType.COMMERCIAL,
            symbol=None,
        )
        result = engine.detect_symbols(image)
        assert result.enabled is False
        assert result.detections == []
        assert result.provenance is None
        assert result.slot is None
        assert any("no symbol detector resolved" in n for n in result.notes)

    def test_symbol_adapter_raises_is_swallowed(self, image: np.ndarray):
        symbol_adapter = _FakeSymbolAdapter(
            detections=[], raises=RuntimeError("inference blew up")
        )
        engine = MLEngine(
            building_type=BuildingType.RESIDENTIAL,
            symbol=_mk_resolved_detector(
                slot="symbol_detector",
                detector_source=DetectorSource.SYMBOL_DETECTOR,
                model_id="symbol_yolov8",
                adapter=symbol_adapter,
            ),
        )
        result = engine.detect_symbols(image)
        assert result.enabled is True  # was enabled, just crashed
        assert result.detections == []
        assert result.provenance is not None
        assert any("inference blew up" in n for n in result.notes)


# ===========================================================================
# MLEngine.from_loader — manifest-driven resolution
# ===========================================================================


def _tagged_manifest(
    tmp_path: Path,
    enabled_primary: bool = True,
    primary_confidence_threshold: Optional[float] = 0.33,
) -> Path:
    """Build a minimal manifest with all three slots tagged.

    The slots point at actual files on disk so the backend can
    ``available`` / ``fetch`` them without the tests needing to mock
    the backend.  Tests then mock ``build_model`` to avoid torch.
    """

    weights_dir = tmp_path / "weights"
    weights_dir.mkdir()
    (weights_dir / "primary.bin").write_bytes(b"fake-primary")
    (weights_dir / "fallback.bin").write_bytes(b"fake-fallback")
    (weights_dir / "symbols.bin").write_bytes(b"fake-symbols")

    threshold_line = (
        f"    confidence_threshold: {primary_confidence_threshold}\n"
        if primary_confidence_threshold is not None
        else ""
    )

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        f"""schema_version: "1.0.0"
models:
  primary_residential:
    enabled: {str(enabled_primary).lower()}
    architecture: cubicasa_hg
    kind: {KIND_WALL_PRIMARY}
    building_types: [RESIDENTIAL, MIXED_USE]
{threshold_line}    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: primary.bin
    num_classes: 44
    source:
      local_path: {weights_dir / 'primary.bin'}
  fallback_universal:
    enabled: true
    architecture: yolov8_seg
    kind: {KIND_WALL_FALLBACK}
    model_id: yolo_wall_seg
    model_version: "1.0.0"
    filename: fallback.bin
    source:
      local_path: {weights_dir / 'fallback.bin'}
  symbols_universal:
    enabled: true
    architecture: yolov8
    kind: {KIND_SYMBOL_DETECTOR}
    model_id: symbol_yolov8
    model_version: "1.0.0"
    filename: symbols.bin
    source:
      local_path: {weights_dir / 'symbols.bin'}
""",
        encoding="utf-8",
    )
    return manifest_path


class TestFromLoader:
    def test_resolves_primary_fallback_symbol_for_residential(
        self, tmp_path: Path
    ):
        manifest_path = _tagged_manifest(tmp_path)
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)

        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: (
                np.zeros((21, 1, 1), np.float32),
                np.zeros((12, 1, 1), np.float32),
                np.zeros((11, 1, 1), np.float32),
            ),
        ):
            engine = MLEngine.from_loader(
                loader,
                building_type=BuildingType.RESIDENTIAL,
                run_id="run-from-loader",
            )

        assert engine.primary_slot == "primary_residential"
        assert engine.fallback_slot == "fallback_universal"
        assert engine.symbol_slot == "symbols_universal"
        assert engine.has_primary_wall
        assert engine.has_fallback_wall
        assert engine.has_symbol_detector

    def test_manifest_hash_flows_onto_provenance(self, tmp_path: Path):
        manifest_path = _tagged_manifest(tmp_path)
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)
        expected_hash = manifest.manifest_hash()

        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: None,
        ):
            engine = MLEngine.from_loader(
                loader, building_type=BuildingType.RESIDENTIAL
            )
        assert engine._wall_primary is not None
        assert engine._wall_primary.provenance.weights_manifest_hash == expected_hash
        assert engine._wall_fallback is not None
        assert engine._wall_fallback.provenance.weights_manifest_hash == expected_hash
        assert engine._symbol is not None
        assert engine._symbol.provenance.weights_manifest_hash == expected_hash

    def test_primary_disabled_falls_through_to_no_primary(self, tmp_path: Path):
        manifest_path = _tagged_manifest(tmp_path, enabled_primary=False)
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)
        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: None,
        ):
            engine = MLEngine.from_loader(
                loader, building_type=BuildingType.RESIDENTIAL
            )
        assert engine.primary_slot is None
        assert engine.has_primary_wall is False
        assert engine.fallback_slot == "fallback_universal"
        assert engine.has_fallback_wall is True

    def test_manifest_confidence_threshold_is_honoured(self, tmp_path: Path):
        """Per-slot tuning lives on the manifest — the engine must
        pick it up without any code change."""

        manifest_path = _tagged_manifest(
            tmp_path, primary_confidence_threshold=0.42
        )
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)
        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: None,
        ):
            engine = MLEngine.from_loader(
                loader, building_type=BuildingType.RESIDENTIAL
            )
        assert engine.confidence_threshold == pytest.approx(0.42)

    def test_caller_threshold_wins_over_manifest(self, tmp_path: Path):
        """An explicit factory argument overrides the manifest, so
        smoke tests and debug runs can probe different thresholds
        without editing the YAML."""

        manifest_path = _tagged_manifest(
            tmp_path, primary_confidence_threshold=0.42
        )
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)
        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: None,
        ):
            engine = MLEngine.from_loader(
                loader,
                building_type=BuildingType.RESIDENTIAL,
                confidence_threshold=0.11,
            )
        assert engine.confidence_threshold == pytest.approx(0.11)

    def test_falls_back_to_default_when_manifest_omits_threshold(
        self, tmp_path: Path
    ):
        """No manifest value and no caller override → module default.
        Regression gate so a silent field rename doesn't strand the
        engine on zero threshold."""

        from src.cv.ml_engine import DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD

        manifest_path = _tagged_manifest(
            tmp_path, primary_confidence_threshold=None
        )
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)
        with patch.object(
            WeightsLoader, "build_model", return_value=MagicMock()
        ), patch(
            "src.cv.ml_engine._load_cubicasa_split_prediction",
            return_value=lambda *_a, **_k: None,
        ):
            engine = MLEngine.from_loader(
                loader, building_type=BuildingType.RESIDENTIAL
            )
        assert engine.confidence_threshold == pytest.approx(
            DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD
        )

    def test_build_model_failure_is_graceful(self, tmp_path: Path):
        """If ``build_model`` raises (e.g. torch not installed in this env),
        the engine must still come up — just with that slot missing."""

        manifest_path = _tagged_manifest(tmp_path)
        manifest = WeightsManifest.load(manifest_path)
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "weights", repo_root=tmp_path
        )
        loader = WeightsLoader(manifest=manifest, backend=backend)

        def _boom(self, name):
            raise RuntimeError(f"cannot build {name}: torch missing")

        with patch.object(WeightsLoader, "build_model", _boom):
            engine = MLEngine.from_loader(
                loader, building_type=BuildingType.RESIDENTIAL
            )
        # Every slot failed to build → every handle is None, and
        # segment_walls / detect_symbols gracefully degrade.
        assert not engine.has_primary_wall
        assert not engine.has_fallback_wall
        assert not engine.has_symbol_detector

        img = np.zeros((16, 32, 3), np.uint8)
        wall_result = engine.segment_walls(img)
        assert wall_result.provenance.model_id == "ml_engine_stub"
        symbol_result = engine.detect_symbols(img)
        assert symbol_result.enabled is False
