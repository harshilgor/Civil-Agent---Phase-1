"""Unit tests for :class:`backend.weights.loader.WeightsLoader`.

Model-building tests are gated behind ``@pytest.mark.requires_weights`` —
they only make sense when real checkpoints are on disk, and the default
collection skips them automatically.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.weights.loader import (
    ResolvedWeights,
    WeightsLoader,
    WeightsLoaderError,
)
from backend.weights.manifest import Architecture, WeightsManifest
from backend.weights.backends import LocalWeightsBackend
from src.schema.enums import BuildingType, DetectorSource
from src.schema.provenance import ProvenanceRecord


@pytest.fixture()
def loader(tmp_path: Path, tmp_manifest_path: Path, tmp_weights_artifact) -> WeightsLoader:
    """Build a loader whose local backend already has the wall_segmenter cached."""

    artefact, _sha, _size = tmp_weights_artifact
    weights_dir = tmp_path / "weights-cache"
    weights_dir.mkdir()
    shutil.copy(artefact, weights_dir / artefact.name)

    manifest = WeightsManifest.load(tmp_manifest_path)
    backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
    return WeightsLoader(manifest=manifest, backend=backend)


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


class TestIntrospection:
    def test_is_known(self, loader: WeightsLoader):
        assert loader.is_known("wall_segmenter_residential")
        assert loader.is_known("yolo_wall_seg")
        assert not loader.is_known("invented")

    def test_is_enabled(self, loader: WeightsLoader):
        assert loader.is_enabled("wall_segmenter_residential")
        assert not loader.is_enabled("yolo_wall_seg")  # manifest fixture: disabled
        assert not loader.is_enabled("invented")

    def test_is_available_true_when_cached(self, loader: WeightsLoader):
        assert loader.is_available("wall_segmenter_residential")

    def test_is_available_false_when_disabled(self, loader: WeightsLoader):
        assert not loader.is_available("yolo_wall_seg")

    def test_is_available_false_when_unknown(self, loader: WeightsLoader):
        assert not loader.is_available("invented")

    def test_manifest_hash_stable(self, loader: WeightsLoader):
        assert loader.manifest_hash == loader.manifest.manifest_hash()


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


class TestResolve:
    def test_happy_path(self, loader: WeightsLoader):
        rw = loader.resolve("wall_segmenter_residential")
        assert isinstance(rw, ResolvedWeights)
        assert rw.name == "wall_segmenter_residential"
        assert rw.architecture is Architecture.CUBICASA_HG
        assert rw.model_id == "cubicasa_hg_v1"
        assert rw.model_version == "1.0.0"
        assert rw.num_classes == 44
        assert rw.path.is_file()
        assert rw.manifest_hash == loader.manifest_hash

    def test_params_is_defensive_copy(self, loader: WeightsLoader):
        rw = loader.resolve("wall_segmenter_residential")
        params = rw.params
        params["mutated"] = True
        # Re-resolve and confirm the manifest entry wasn't mutated.
        rw2 = loader.resolve("wall_segmenter_residential")
        assert "mutated" not in rw2.params

    def test_unknown_slot_raises(self, loader: WeightsLoader):
        with pytest.raises(WeightsLoaderError, match="No manifest entry"):
            loader.resolve("invented")

    def test_disabled_slot_raises(self, loader: WeightsLoader):
        with pytest.raises(WeightsLoaderError, match="disabled"):
            loader.resolve("yolo_wall_seg")

    def test_missing_file_raises_loader_error(self, tmp_path: Path):
        """Loader wraps backend errors in WeightsLoaderError."""

        manifest_path = tmp_path / "s3_only.yaml"
        manifest_path.write_text(
            """
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: cubicasa_hg_v1.pkl
    source:
      s3_key: models/cubicasa/cubicasa_hg_v1.pkl
""".lstrip(),
            encoding="utf-8",
        )
        manifest = WeightsManifest.load(manifest_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        backend = LocalWeightsBackend(weights_dir=empty_dir, repo_root=empty_dir)
        loader = WeightsLoader(manifest=manifest, backend=backend)
        with pytest.raises(WeightsLoaderError, match="Could not fetch"):
            loader.resolve("wall_segmenter_residential")


# ---------------------------------------------------------------------------
# get_if_enabled()
# ---------------------------------------------------------------------------


class TestGetIfEnabled:
    def test_returns_resolved_when_enabled(self, loader: WeightsLoader):
        rw = loader.get_if_enabled("wall_segmenter_residential")
        assert rw is not None
        assert rw.name == "wall_segmenter_residential"

    def test_returns_none_when_disabled(self, loader: WeightsLoader):
        assert loader.get_if_enabled("yolo_wall_seg") is None

    def test_returns_none_when_unknown(self, loader: WeightsLoader):
        assert loader.get_if_enabled("invented") is None

    def test_returns_none_when_backend_fails(self, tmp_path: Path):
        manifest_path = tmp_path / "s3_only.yaml"
        manifest_path.write_text(
            """
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: cubicasa_hg_v1.pkl
    source:
      s3_key: models/cubicasa/cubicasa_hg_v1.pkl
""".lstrip(),
            encoding="utf-8",
        )
        manifest = WeightsManifest.load(manifest_path)
        empty = tmp_path / "empty"
        empty.mkdir()
        backend = LocalWeightsBackend(weights_dir=empty, repo_root=empty)
        loader = WeightsLoader(manifest=manifest, backend=backend)
        assert loader.get_if_enabled("wall_segmenter_residential") is None


# ---------------------------------------------------------------------------
# to_provenance()
# ---------------------------------------------------------------------------


class TestToProvenance:
    def test_defaults(self, loader: WeightsLoader):
        rw = loader.resolve("wall_segmenter_residential")
        prov = rw.to_provenance()
        assert isinstance(prov, ProvenanceRecord)
        assert prov.detector_source is DetectorSource.CUBICASA_HG
        assert prov.model_id == "cubicasa_hg_v1"
        assert prov.model_version == "1.0.0"
        assert prov.weights_manifest_hash == loader.manifest_hash
        assert prov.run_id is None
        assert prov.confidence_from_model is None

    def test_overrides(self, loader: WeightsLoader):
        rw = loader.resolve("wall_segmenter_residential")
        prov = rw.to_provenance(
            run_id="job-123",
            confidence_from_model=0.87,
            detector_source=DetectorSource.SMP_UNET,
            notes="rerun with TTA",
        )
        assert prov.run_id == "job-123"
        assert prov.confidence_from_model == 0.87
        assert prov.detector_source is DetectorSource.SMP_UNET
        assert prov.notes == "rerun with TTA"


# ---------------------------------------------------------------------------
# build_model — requires real weights; skipped by default.
# ---------------------------------------------------------------------------


@pytest.mark.requires_weights
class TestBuildModel:
    def test_cubicasa_hg_builds(self, loader: WeightsLoader):
        model = loader.build_model("wall_segmenter_residential")
        assert model is not None
        assert hasattr(model, "eval")


# ---------------------------------------------------------------------------
# from_env — integration with src.config.Settings
# ---------------------------------------------------------------------------


class TestFromEnv:
    def test_uses_settings_manifest_path(self, tmp_path: Path,
                                         tmp_manifest_path: Path,
                                         tmp_weights_artifact,
                                         monkeypatch: pytest.MonkeyPatch):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        from src.config import settings

        monkeypatch.setattr(settings, "weights_manifest_path", tmp_manifest_path,
                            raising=False)
        monkeypatch.setattr(settings, "weights_backend", "local", raising=False)
        monkeypatch.setattr(settings, "weights_dir", weights_dir, raising=False)

        loader = WeightsLoader.from_env()
        assert loader.is_available("wall_segmenter_residential")
        rw = loader.resolve("wall_segmenter_residential")
        assert rw.path.is_file()


# ---------------------------------------------------------------------------
# Step 7 — BuildingType-aware slot selection
# ---------------------------------------------------------------------------


def _tagged_manifest_body(local_path: Path, sha: str, size: int) -> str:
    """Manifest body with ``kind`` + ``building_types`` tags on every slot.

    Covers three interesting shapes:
      * ``wall_segmenter_residential`` — enabled, RESIDENTIAL + MIXED_USE
      * ``wall_segmenter_commercial``  — enabled, COMMERCIAL
      * ``wall_segmenter_universal``   — enabled, no building_types (fallback)
      * ``wall_segmenter_disabled``    — disabled, INSTITUTIONAL — proves
        disabled entries are ignored even when tags match
    """

    return f"""
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    kind: wall_segmenter
    building_types: [RESIDENTIAL, MIXED_USE]
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: {local_path.name}
    sha256: {sha}
    size_bytes: {size}
    num_classes: 44
    source:
      local_path: {local_path.as_posix()}

  wall_segmenter_commercial:
    enabled: true
    architecture: smp_unet
    kind: wall_segmenter
    building_types: [COMMERCIAL]
    model_id: smp_unet_cc5k
    model_version: "0.2.0"
    filename: smp_unet_cc5k.pth
    num_classes: 7
    source:
      s3_key: models/wall_segmenter/smp_unet_cc5k.pth

  wall_segmenter_universal:
    enabled: true
    architecture: yolov8_seg
    kind: wall_segmenter
    model_id: yolo_wall_seg
    model_version: "0.1.0"
    filename: yolo_wall_seg_v0_1.pt
    source:
      s3_key: models/yolo/yolo_wall_seg_v0_1.pt

  wall_segmenter_disabled:
    enabled: false
    architecture: yolov8
    kind: wall_segmenter
    building_types: [INSTITUTIONAL]
    model_id: disabled
    model_version: "0.0.1"
    filename: disabled.pt
    source:
      s3_key: models/wall_segmenter/disabled.pt
""".lstrip()


@pytest.fixture()
def tagged_loader(tmp_path: Path, tmp_weights_artifact) -> WeightsLoader:
    """Loader built against a manifest that tags every slot with ``kind``
    and ``building_types`` — used exclusively by the Step-7 routing
    tests.  The residential slot's artefact is cached locally so
    ``resolve_for_building_type`` can actually fetch it."""

    artefact, sha, size = tmp_weights_artifact
    weights_dir = tmp_path / "weights-cache"
    weights_dir.mkdir()
    shutil.copy(artefact, weights_dir / artefact.name)

    manifest_path = tmp_path / "tagged_manifest.yaml"
    manifest_path.write_text(
        _tagged_manifest_body(artefact, sha, size), encoding="utf-8"
    )
    manifest = WeightsManifest.load(manifest_path)
    backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
    return WeightsLoader(manifest=manifest, backend=backend)


class TestSelectSlotForBuildingType:
    def test_typed_match_wins_over_universal(self, tagged_loader: WeightsLoader):
        """RESIDENTIAL → residential slot, never the universal fallback."""
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.RESIDENTIAL
        )
        assert slot == "wall_segmenter_residential"

    def test_commercial_matches_commercial_slot(self, tagged_loader: WeightsLoader):
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.COMMERCIAL
        )
        assert slot == "wall_segmenter_commercial"

    def test_mixed_use_matches_residential(self, tagged_loader: WeightsLoader):
        """MIXED_USE is listed on the residential entry's building_types."""
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.MIXED_USE
        )
        assert slot == "wall_segmenter_residential"

    def test_unmatched_falls_back_to_universal(self, tagged_loader: WeightsLoader):
        """INDUSTRIAL isn't on any typed slot → universal fallback."""
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.INDUSTRIAL
        )
        assert slot == "wall_segmenter_universal"

    def test_unknown_falls_back_to_universal(self, tagged_loader: WeightsLoader):
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.UNKNOWN
        )
        assert slot == "wall_segmenter_universal"

    def test_disabled_slot_ignored_even_when_tagged(
        self, tagged_loader: WeightsLoader
    ):
        """INSTITUTIONAL is on wall_segmenter_disabled only; that entry
        is disabled, so the universal fallback should be returned."""
        slot = tagged_loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.INSTITUTIONAL
        )
        assert slot == "wall_segmenter_universal"

    def test_unknown_kind_returns_none(self, tagged_loader: WeightsLoader):
        slot = tagged_loader.select_slot_for_building_type(
            kind="symbol_detector", building_type=BuildingType.COMMERCIAL
        )
        assert slot is None

    def test_untagged_legacy_manifest_returns_none(self, loader: WeightsLoader):
        """The default `loader` fixture's manifest carries no ``kind``
        tags — resolution for any building type should therefore return
        ``None`` (backwards compat guarantee)."""

        slot = loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.RESIDENTIAL
        )
        assert slot is None


class TestResolveForBuildingType:
    def test_resolves_to_cached_artifact(self, tagged_loader: WeightsLoader):
        rw = tagged_loader.resolve_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.RESIDENTIAL
        )
        assert rw is not None
        assert rw.name == "wall_segmenter_residential"
        assert rw.path.is_file()

    def test_no_match_returns_none(self, tagged_loader: WeightsLoader):
        rw = tagged_loader.resolve_for_building_type(
            kind="nonexistent_kind", building_type=BuildingType.RESIDENTIAL
        )
        assert rw is None

    def test_backend_failure_returns_none(self, tagged_loader: WeightsLoader):
        """COMMERCIAL slot references an S3-only source with no backend —
        :meth:`resolve_for_building_type` swallows the fetch failure and
        returns ``None`` so the worker can continue without a detector."""

        rw = tagged_loader.resolve_for_building_type(
            kind="wall_segmenter", building_type=BuildingType.COMMERCIAL
        )
        assert rw is None


class TestWeightsEntryTagValidation:
    def test_empty_building_types_list_rejected(self, tmp_path: Path) -> None:
        """An explicit empty list is ambiguous — use ``null`` for universal
        or list at least one enum member.  The manifest validator must
        reject this so misconfigured YAMLs fail loudly."""

        from backend.weights.manifest import ManifestError

        manifest_path = tmp_path / "bad.yaml"
        manifest_path.write_text(
            """
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    kind: wall_segmenter
    building_types: []
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: cubicasa_hg_v1.pkl
    source:
      s3_key: models/wall_segmenter/cubicasa_hg_v1.pkl
""".lstrip(),
            encoding="utf-8",
        )
        with pytest.raises(ManifestError, match="building_types"):
            WeightsManifest.load(manifest_path)
