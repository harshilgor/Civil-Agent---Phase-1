"""Unit tests for :mod:`backend.weights.manifest`."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.weights.manifest import (
    MANIFEST_SCHEMA_VERSION,
    Architecture,
    ManifestError,
    WeightsEntry,
    WeightsManifest,
    WeightsSource,
)


class TestWeightsSource:
    def test_requires_at_least_one_location(self):
        with pytest.raises(Exception, match="local_path or s3_key"):
            WeightsEntry(
                architecture=Architecture.CUBICASA_HG,
                model_id="x",
                model_version="1.0.0",
                filename="x.pkl",
                source=WeightsSource(),
            )

    def test_rejects_absolute_s3_key(self):
        with pytest.raises(Exception, match="bucket-relative"):
            WeightsSource(s3_key="/models/x.pkl")

    def test_rejects_scheme_in_s3_key(self):
        with pytest.raises(Exception, match="bucket-relative"):
            WeightsSource(s3_key="s3://bucket/models/x.pkl")


class TestWeightsEntryValidation:
    def _kwargs(self, **overrides):
        base = dict(
            architecture=Architecture.CUBICASA_HG,
            model_id="cubicasa_hg_v1",
            model_version="1.0.0",
            filename="cubicasa_hg_v1.pkl",
            source=WeightsSource(s3_key="models/cubicasa/cubicasa_hg_v1.pkl"),
        )
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        e = WeightsEntry(**self._kwargs())
        assert e.enabled is True
        assert e.architecture is Architecture.CUBICASA_HG

    def test_invalid_version_format(self):
        with pytest.raises(Exception, match="model_version"):
            WeightsEntry(**self._kwargs(model_version="1.0"))

    def test_invalid_sha256(self):
        with pytest.raises(Exception, match="sha256"):
            WeightsEntry(**self._kwargs(sha256="not-hex"))

    def test_invalid_architecture(self):
        with pytest.raises(Exception):
            WeightsEntry(**self._kwargs(architecture="floor_net"))


class TestWeightsManifestLoad:
    def test_load_fixture(self, tmp_manifest_path: Path):
        manifest = WeightsManifest.load(tmp_manifest_path)
        assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
        assert set(manifest.models) == {
            "wall_segmenter_residential",
            "wall_segmenter_commercial",
            "yolo_wall_seg",
        }

    def test_enabled_models_filter(self, tmp_manifest_path: Path):
        manifest = WeightsManifest.load(tmp_manifest_path)
        enabled = manifest.enabled_models()
        assert list(enabled) == ["wall_segmenter_residential"]

    def test_get_unknown_slot_raises(self, tmp_manifest_path: Path):
        manifest = WeightsManifest.load(tmp_manifest_path)
        with pytest.raises(ManifestError, match="No manifest entry"):
            manifest.get("no_such_model")

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(ManifestError, match="not found"):
            WeightsManifest.load(tmp_path / "missing.yaml")

    def test_bad_yaml(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("models: [this: is: not: yaml", encoding="utf-8")
        with pytest.raises(ManifestError, match="malformed"):
            WeightsManifest.load(path)

    def test_empty_models_rejected(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text('schema_version: "1.0.0"\nmodels: {}\n', encoding="utf-8")
        with pytest.raises(ManifestError, match="at least one entry"):
            WeightsManifest.load(path)

    def test_unsupported_schema_version(self, tmp_path: Path):
        path = tmp_path / "wrong.yaml"
        path.write_text(
            """
schema_version: "2.0.0"
models:
  x:
    architecture: cubicasa_hg
    model_id: x
    model_version: "1.0.0"
    filename: x.pkl
    source:
      s3_key: x.pkl
""".lstrip(),
            encoding="utf-8",
        )
        with pytest.raises(ManifestError, match="Unsupported manifest schema_version"):
            WeightsManifest.load(path)

    def test_extra_top_level_key_rejected(self, tmp_path: Path):
        path = tmp_path / "extra.yaml"
        path.write_text(
            """
schema_version: "1.0.0"
extra_top: value
models:
  x:
    architecture: cubicasa_hg
    model_id: x
    model_version: "1.0.0"
    filename: x.pkl
    source:
      s3_key: x.pkl
""".lstrip(),
            encoding="utf-8",
        )
        with pytest.raises(ManifestError):
            WeightsManifest.load(path)


class TestManifestHash:
    def test_stable_across_loads(self, tmp_manifest_path: Path):
        a = WeightsManifest.load(tmp_manifest_path).manifest_hash()
        b = WeightsManifest.load(tmp_manifest_path).manifest_hash()
        assert a == b
        assert len(a) == 64

    def test_changes_when_entry_flipped(self, tmp_manifest_path: Path):
        m1 = WeightsManifest.load(tmp_manifest_path)
        h1 = m1.manifest_hash()

        # Toggle yolo_wall_seg from disabled to enabled and confirm drift.
        m2 = m1.model_copy(deep=True)
        m2.models["yolo_wall_seg"].enabled = True
        assert m2.manifest_hash() != h1

    def test_repository_manifest_loads(self):
        """The manifest file that actually ships with the repository must
        validate — catches breakage of the real config/weights_manifest.yaml."""

        repo_manifest = (
            Path(__file__).resolve().parents[2]
            / "config"
            / "weights_manifest.yaml"
        )
        if not repo_manifest.exists():  # defensive; should always exist
            pytest.skip("config/weights_manifest.yaml not present in tree")
        manifest = WeightsManifest.load(repo_manifest)
        assert "wall_segmenter_residential" in manifest.models
        enabled = manifest.enabled_models()
        assert "wall_segmenter_residential" in enabled
