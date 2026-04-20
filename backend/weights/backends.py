"""Pluggable fetch backends for the weights manifest.

Two backends ship today:

* :class:`LocalWeightsBackend` — the default.  Resolves the artefact against
  ``settings.weights_dir`` (or the repository root when ``entry.source.local_path``
  is a repo-relative path), verifies the SHA-256 if the manifest declares one,
  and returns the on-disk path.  Zero ``boto3`` imports.

* :class:`S3WeightsBackend` — production path.  Lazy-imports ``boto3`` on first
  use, caches downloads under ``settings.weights_dir`` keyed by SHA-256, and
  verifies the integrity of the downloaded artefact.  Only constructed when
  ``settings.weights_backend == "s3"`` *and* ``settings.s3_bucket`` is set, so
  the rest of the codebase pays no cost for the S3 path until it is explicitly
  wired up.

The factory :func:`get_backend` consults :class:`~src.config.Settings`; tests
always drive the local backend directly with a temporary directory and never
touch ``boto3``.
"""

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .manifest import WeightsEntry

_READ_CHUNK = 1 << 20  # 1 MiB


class WeightsBackendError(RuntimeError):
    """Raised on any backend IO / integrity failure."""


def sha256_of_file(path: Path, *, chunk_size: int = _READ_CHUNK) -> str:
    """Stream-hash a file and return the lowercase hex SHA-256."""

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _verify(path: Path, entry: WeightsEntry) -> None:
    if entry.size_bytes is not None:
        actual = path.stat().st_size
        if actual != entry.size_bytes:
            raise WeightsBackendError(
                f"Size mismatch for {entry.model_id} at {path}: "
                f"manifest says {entry.size_bytes}, file is {actual}"
            )
    if entry.sha256 is not None:
        actual = sha256_of_file(path)
        if actual.lower() != entry.sha256.lower():
            raise WeightsBackendError(
                f"SHA-256 mismatch for {entry.model_id} at {path}: "
                f"manifest says {entry.sha256}, file is {actual}"
            )


class WeightsBackend(ABC):
    """Abstract fetch strategy for a :class:`WeightsEntry`."""

    name: str

    @abstractmethod
    def available(self, entry: WeightsEntry) -> bool:
        """Return True when ``entry`` can be fetched without further work."""

    @abstractmethod
    def fetch(self, entry: WeightsEntry) -> Path:
        """Return an absolute path to the weights file, fetching if needed.

        Always verifies ``size_bytes`` / ``sha256`` when the manifest
        supplies them.  Raises :class:`WeightsBackendError` on any failure.
        """


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------


class LocalWeightsBackend(WeightsBackend):
    """Resolve weights from ``weights_dir`` or a repo-relative local path.

    Lookup order for each entry:

      1. ``weights_dir / entry.filename`` — the canonical cache location
         populated by ``scripts/fetch_weights.py`` or by bind-mounting a
         shared volume in production.
      2. ``repo_root / entry.source.local_path`` when the manifest names
         a vendored checkpoint.

    The first existing candidate wins; subsequent verification is applied
    uniformly regardless of which branch matched.
    """

    name = "local"

    def __init__(self, *, weights_dir: Path, repo_root: Optional[Path] = None) -> None:
        self.weights_dir = Path(weights_dir)
        self.repo_root = (
            Path(repo_root)
            if repo_root is not None
            else Path(__file__).resolve().parents[2]
        )

    def _candidates(self, entry: WeightsEntry) -> list[Path]:
        paths: list[Path] = [self.weights_dir / entry.filename]
        if entry.source.local_path is not None:
            vendored = entry.source.local_path
            if not vendored.is_absolute():
                vendored = self.repo_root / vendored
            paths.append(vendored)
        return paths

    def _existing(self, entry: WeightsEntry) -> Optional[Path]:
        for candidate in self._candidates(entry):
            if candidate.is_file():
                return candidate
        return None

    def available(self, entry: WeightsEntry) -> bool:
        return self._existing(entry) is not None

    def fetch(self, entry: WeightsEntry) -> Path:
        path = self._existing(entry)
        if path is None:
            attempted = "\n  - ".join(str(p) for p in self._candidates(entry))
            raise WeightsBackendError(
                f"Local weights for {entry.model_id} ({entry.filename}) not "
                f"found.  Tried:\n  - {attempted}\n"
                "Run `python scripts/fetch_weights.py` or place the file in "
                "one of the candidate paths."
            )
        _verify(path, entry)
        return path


# ---------------------------------------------------------------------------
# S3 backend (lazy boto3)
# ---------------------------------------------------------------------------


class S3WeightsBackend(WeightsBackend):
    """Download weights from S3, cache under ``weights_dir``, verify.

    The ``boto3`` client is created lazily on first use so the import cost is
    never paid by tests or by Phase 1 runs that use the local backend.
    """

    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        weights_dir: Path,
        region: str = "us-east-1",
        client: object | None = None,
    ) -> None:
        if not bucket:
            raise WeightsBackendError(
                "S3WeightsBackend requires a bucket name; set settings.s3_bucket "
                "or pass bucket= explicitly."
            )
        self.bucket = bucket
        self.region = region
        self.weights_dir = Path(weights_dir)
        self._client = client

    def _get_client(self) -> object:
        if self._client is None:
            try:
                import boto3  # noqa: PLC0415  (lazy on purpose)
            except ImportError as exc:
                raise WeightsBackendError(
                    "boto3 is not installed; install the 's3' extra "
                    "(`pip install .[s3]`) or switch WEIGHTS_BACKEND=local."
                ) from exc
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def _cache_path(self, entry: WeightsEntry) -> Path:
        return self.weights_dir / entry.filename

    def available(self, entry: WeightsEntry) -> bool:
        if self._cache_path(entry).is_file():
            return True
        if entry.source.s3_key is None:
            return False
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=entry.source.s3_key)
            return True
        except Exception:
            return False

    def fetch(self, entry: WeightsEntry) -> Path:
        if entry.source.s3_key is None:
            raise WeightsBackendError(
                f"Entry {entry.model_id} has no s3_key; cannot fetch via S3"
            )
        cache = self._cache_path(entry)
        if not cache.is_file():
            self.weights_dir.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(cache.suffix + ".partial")
            client = self._get_client()
            try:
                client.download_file(
                    Bucket=self.bucket,
                    Key=entry.source.s3_key,
                    Filename=str(tmp),
                )
            except Exception as exc:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise WeightsBackendError(
                    f"S3 download failed for s3://{self.bucket}/"
                    f"{entry.source.s3_key}: {exc}"
                ) from exc
            shutil.move(str(tmp), str(cache))
        _verify(cache, entry)
        return cache


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_backend(
    name: Optional[str] = None,
    *,
    weights_dir: Optional[Path] = None,
    s3_bucket: Optional[str] = None,
    aws_region: Optional[str] = None,
) -> WeightsBackend:
    """Construct the backend named by ``name`` (or ``settings.weights_backend``).

    Keyword arguments override the corresponding settings values and are the
    only way tests can dial in an isolated temp directory.
    """

    # Lazy import of settings so the weights package does not pull in
    # pydantic-settings at import time (keeps ``fetch_weights.py`` snappy).
    from src.config import settings  # noqa: PLC0415

    resolved_name = (name or settings.weights_backend).lower()
    wdir = Path(weights_dir) if weights_dir is not None else Path(settings.weights_dir)

    if resolved_name == "local":
        return LocalWeightsBackend(weights_dir=wdir)
    if resolved_name == "s3":
        bucket = s3_bucket or settings.s3_bucket
        region = aws_region or settings.aws_region
        if not bucket:
            raise WeightsBackendError(
                "WEIGHTS_BACKEND=s3 but S3_BUCKET is unset; configure settings."
            )
        return S3WeightsBackend(bucket=bucket, weights_dir=wdir, region=region)
    raise WeightsBackendError(
        f"Unknown weights backend {resolved_name!r}; expected 'local' or 's3'."
    )
