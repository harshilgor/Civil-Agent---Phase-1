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
from src.schema.enums import DetectorSource
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
