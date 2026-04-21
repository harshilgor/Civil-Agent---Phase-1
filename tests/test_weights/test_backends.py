"""Unit tests for :mod:`backend.weights.backends`."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.weights.backends import (
    LocalWeightsBackend,
    S3WeightsBackend,
    WeightsBackendError,
    get_backend,
    sha256_of_file,
)
from backend.weights.manifest import (
    Architecture,
    WeightsEntry,
    WeightsManifest,
    WeightsSource,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    filename: str = "cubicasa_hg_v1.pkl",
    local_path: Path | None = None,
    s3_key: str | None = "models/cubicasa/cubicasa_hg_v1.pkl",
    sha256: str | None = None,
    size_bytes: int | None = None,
    enabled: bool = True,
) -> WeightsEntry:
    return WeightsEntry(
        enabled=enabled,
        architecture=Architecture.CUBICASA_HG,
        model_id="cubicasa_hg_v1",
        model_version="1.0.0",
        filename=filename,
        sha256=sha256,
        size_bytes=size_bytes,
        source=WeightsSource(local_path=local_path, s3_key=s3_key),
    )


# ---------------------------------------------------------------------------
# sha256_of_file
# ---------------------------------------------------------------------------


class TestSha256OfFile:
    def test_matches_expected_digest(self, tmp_path: Path):
        payload = b"hello world" * 1000
        f = tmp_path / "blob.bin"
        f.write_bytes(payload)
        assert sha256_of_file(f) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# LocalWeightsBackend
# ---------------------------------------------------------------------------


class TestLocalWeightsBackend:
    def test_hit_in_weights_dir(self, tmp_path: Path, tmp_weights_artifact):
        artefact, sha, size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        # Place the same payload in the cache (not the vendor path).
        (weights_dir / artefact.name).write_bytes(artefact.read_bytes())

        backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
        entry = _make_entry(filename=artefact.name, sha256=sha, size_bytes=size,
                            local_path=None)

        assert backend.available(entry)
        resolved = backend.fetch(entry)
        assert resolved == weights_dir / artefact.name

    def test_hit_via_vendor_local_path(self, tmp_path: Path, tmp_weights_artifact):
        artefact, sha, size = tmp_weights_artifact
        # Cache dir is empty — force the fallback to ``source.local_path``.
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()

        # Fake vendor tree under tmp_path.
        vendored_rel = Path("vendors/fake/weights") / artefact.name
        vendored_abs = tmp_path / vendored_rel
        vendored_abs.parent.mkdir(parents=True)
        vendored_abs.write_bytes(artefact.read_bytes())

        backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
        entry = _make_entry(
            filename=artefact.name,
            sha256=sha,
            size_bytes=size,
            local_path=vendored_rel,
        )

        assert backend.available(entry)
        resolved = backend.fetch(entry)
        assert resolved == vendored_abs

    def test_miss_raises_with_helpful_message(self, tmp_path: Path):
        backend = LocalWeightsBackend(
            weights_dir=tmp_path / "no-cache",
            repo_root=tmp_path,
        )
        entry = _make_entry(filename="nope.pkl", local_path=None)

        assert not backend.available(entry)
        with pytest.raises(WeightsBackendError, match="not found"):
            backend.fetch(entry)

    def test_sha256_mismatch_raises(self, tmp_path: Path, tmp_weights_artifact):
        artefact, _sha, size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        (weights_dir / artefact.name).write_bytes(artefact.read_bytes())

        # Supply a different (but valid-format) sha256.
        wrong_sha = "0" * 64
        backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
        entry = _make_entry(filename=artefact.name, sha256=wrong_sha,
                            size_bytes=size, local_path=None)

        with pytest.raises(WeightsBackendError, match="SHA-256 mismatch"):
            backend.fetch(entry)

    def test_size_mismatch_raises(self, tmp_path: Path, tmp_weights_artifact):
        artefact, sha, size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        (weights_dir / artefact.name).write_bytes(artefact.read_bytes())

        backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
        entry = _make_entry(
            filename=artefact.name, sha256=sha,
            size_bytes=size + 1, local_path=None,
        )
        with pytest.raises(WeightsBackendError, match="Size mismatch"):
            backend.fetch(entry)

    def test_manifest_without_sha_still_resolves(self, tmp_path: Path,
                                                 tmp_weights_artifact):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        (weights_dir / artefact.name).write_bytes(artefact.read_bytes())

        backend = LocalWeightsBackend(weights_dir=weights_dir, repo_root=tmp_path)
        entry = _make_entry(filename=artefact.name, sha256=None,
                            size_bytes=None, local_path=None)
        resolved = backend.fetch(entry)
        assert resolved.is_file()


# ---------------------------------------------------------------------------
# S3WeightsBackend (fully mocked — never touches the network)
# ---------------------------------------------------------------------------


class TestS3WeightsBackend:
    def test_requires_bucket(self, tmp_path: Path):
        with pytest.raises(WeightsBackendError, match="bucket"):
            S3WeightsBackend(bucket="", weights_dir=tmp_path)

    def test_fetch_downloads_and_caches(self, tmp_path: Path, tmp_weights_artifact):
        artefact, sha, size = tmp_weights_artifact
        payload = artefact.read_bytes()
        cache_dir = tmp_path / "cache"

        def _fake_download(*, Bucket, Key, Filename):  # noqa: N803
            assert Bucket == "my-bucket"
            assert Key == "models/cubicasa/cubicasa_hg_v1.pkl"
            Path(Filename).write_bytes(payload)

        client = MagicMock()
        client.download_file.side_effect = _fake_download
        client.head_object.return_value = {"ContentLength": size}

        backend = S3WeightsBackend(
            bucket="my-bucket",
            weights_dir=cache_dir,
            client=client,
        )
        entry = _make_entry(
            filename=artefact.name,
            sha256=sha,
            size_bytes=size,
            local_path=None,
            s3_key="models/cubicasa/cubicasa_hg_v1.pkl",
        )

        path = backend.fetch(entry)
        assert path == cache_dir / artefact.name
        assert path.read_bytes() == payload
        client.download_file.assert_called_once()

        # Second fetch must be a cache hit (no extra download).
        client.download_file.reset_mock()
        path2 = backend.fetch(entry)
        assert path2 == path
        client.download_file.assert_not_called()

    def test_fetch_propagates_download_failure(self, tmp_path: Path):
        client = MagicMock()
        client.download_file.side_effect = RuntimeError("403 Forbidden")
        backend = S3WeightsBackend(
            bucket="my-bucket",
            weights_dir=tmp_path / "cache",
            client=client,
        )
        entry = _make_entry(
            filename="model.pkl",
            s3_key="models/x/model.pkl",
            local_path=None,
        )
        with pytest.raises(WeightsBackendError, match="S3 download failed"):
            backend.fetch(entry)

    def test_available_uses_head_object(self, tmp_path: Path):
        client = MagicMock()
        backend = S3WeightsBackend(
            bucket="my-bucket",
            weights_dir=tmp_path / "cache",
            client=client,
        )
        entry = _make_entry(
            filename="model.pkl",
            s3_key="models/x/model.pkl",
            local_path=None,
        )

        client.head_object.return_value = {"ContentLength": 1234}
        assert backend.available(entry)

        client.head_object.side_effect = RuntimeError("NoSuchKey")
        assert not backend.available(entry)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetBackendFactory:
    def test_local_backend_explicit(self, tmp_path: Path):
        backend = get_backend("local", weights_dir=tmp_path)
        assert isinstance(backend, LocalWeightsBackend)
        assert backend.weights_dir == tmp_path

    def test_s3_backend_requires_bucket(self, tmp_path: Path, monkeypatch):
        # Ensure settings does not silently provide a bucket.
        from src.config import settings

        monkeypatch.setattr(settings, "s3_bucket", "", raising=False)
        with pytest.raises(WeightsBackendError, match="S3_BUCKET"):
            get_backend("s3", weights_dir=tmp_path)

    def test_unknown_backend(self, tmp_path: Path):
        with pytest.raises(WeightsBackendError, match="Unknown"):
            get_backend("gcs", weights_dir=tmp_path)

    def test_s3_backend_with_bucket_override(self, tmp_path: Path):
        backend = get_backend(
            "s3",
            weights_dir=tmp_path,
            s3_bucket="test-bucket",
            aws_region="us-west-2",
        )
        assert isinstance(backend, S3WeightsBackend)
        assert backend.bucket == "test-bucket"
        assert backend.region == "us-west-2"
        # Importantly, no boto3 client was constructed.
        assert backend._client is None  # noqa: SLF001


class TestDefaultsReadFromSettings:
    def test_weights_dir_default(self, monkeypatch, tmp_path: Path):
        from src.config import settings

        monkeypatch.setattr(settings, "weights_backend", "local", raising=False)
        monkeypatch.setattr(settings, "weights_dir", tmp_path, raising=False)

        backend = get_backend()
        assert isinstance(backend, LocalWeightsBackend)
        assert backend.weights_dir == tmp_path
