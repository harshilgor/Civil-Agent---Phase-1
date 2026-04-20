"""Weights manifest — the single source of truth for every ML model the
perception pipeline is willing to load.

The manifest is a YAML document that enumerates each slot (``wall_segmenter``,
``yolo_wall_seg``, ``symbol_detector``, …) with everything the loader needs:

    * ``architecture``   — which concrete code path instantiates the model
                           (``cubicasa_hg``, ``smp_unet``, ``yolov8_seg`` …)
    * ``model_id`` / ``model_version`` — stable identifiers persisted on every
                                         :class:`~src.schema.provenance.ProvenanceRecord`
    * ``filename``, ``sha256``, ``size_bytes`` — physical artefact integrity
    * ``source``      — where the artefact can be fetched from (local path /
                        S3 key; the :mod:`backend.weights.backends` modules
                        decide which one to honour at runtime)
    * ``params``      — architecture-specific knobs read verbatim by the
                        loader (e.g. ``num_classes`` for the SMP U-Net head,
                        ``tta_rotations`` for CubiCasa)
    * ``enabled``     — per the Phase 1 Q&A, *disabled* entries are silently
                        skipped and the completeness scorer records the
                        missing detector.

The manifest file itself is hashed (canonical-JSON SHA-256) at load time and
that hash is carried on every :class:`ResolvedWeights` handed out, so the
:class:`~src.schema.provenance.ProvenanceRecord` stored with every wall or
room polygon can be traced back to the exact manifest revision that produced
it.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

MANIFEST_SCHEMA_VERSION = "1.0.0"


class ManifestError(RuntimeError):
    """Raised on any manifest parsing / validation failure."""


class Architecture(str, Enum):
    """Concrete code paths the weights loader knows how to instantiate."""

    CUBICASA_HG = "cubicasa_hg"
    SMP_UNET = "smp_unet"
    YOLOV8_SEG = "yolov8_seg"
    YOLOV8 = "yolov8"


class WeightsSource(BaseModel):
    """Where to fetch a weights artefact from.

    ``local_path`` is honoured by :class:`~backend.weights.backends.LocalWeightsBackend`
    (paths are resolved relative to the repository root, or to
    ``settings.weights_dir`` if that is where the artefact has been staged).
    ``s3_key`` is honoured by :class:`~backend.weights.backends.S3WeightsBackend`.

    At least one of the two must be supplied.
    """

    local_path: Optional[Path] = None
    s3_key: Optional[str] = Field(default=None, max_length=1024)

    @field_validator("s3_key")
    @classmethod
    def _no_scheme(cls, v: Optional[str]) -> Optional[str]:
        if v and ("://" in v or v.startswith("/")):
            raise ValueError(
                "s3_key must be a bucket-relative key, e.g. "
                "'models/cubicasa/model_1427.pkl' (no scheme, no leading slash)"
            )
        return v


class WeightsEntry(BaseModel):
    """A single model slot in the manifest."""

    enabled: bool = True
    architecture: Architecture
    model_id: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?$")
    filename: str = Field(..., min_length=1, max_length=256)
    sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    size_bytes: Optional[int] = Field(default=None, ge=0)
    num_classes: Optional[int] = Field(default=None, ge=1)
    params: dict[str, Any] = Field(default_factory=dict)
    source: WeightsSource
    description: Optional[str] = Field(default=None, max_length=512)

    @field_validator("source")
    @classmethod
    def _at_least_one_source(cls, v: WeightsSource) -> WeightsSource:
        if v.local_path is None and v.s3_key is None:
            raise ValueError("source must define at least one of local_path or s3_key")
        return v


class WeightsManifest(BaseModel):
    """Top-level manifest document."""

    schema_version: str = Field(default=MANIFEST_SCHEMA_VERSION)
    models: dict[str, WeightsEntry]

    model_config = {"extra": "forbid"}

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, v: str) -> str:
        if v != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported manifest schema_version {v!r}; "
                f"this build expects {MANIFEST_SCHEMA_VERSION!r}. "
                "Bump the code if you intentionally migrated the schema."
            )
        return v

    @field_validator("models")
    @classmethod
    def _non_empty(cls, v: dict[str, WeightsEntry]) -> dict[str, WeightsEntry]:
        if not v:
            raise ValueError("models section must define at least one entry")
        return v

    # -- IO -----------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "WeightsManifest":
        """Parse a manifest YAML file.

        Raises :class:`ManifestError` on any IO or validation failure.
        """

        p = Path(path)
        if not p.exists():
            raise ManifestError(f"Manifest file not found: {p}")
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ManifestError(f"Manifest YAML is malformed ({p}): {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestError(
                f"Manifest must be a YAML mapping at the top level ({p}); "
                f"got {type(raw).__name__}"
            )
        try:
            return cls.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError + anything else
            raise ManifestError(f"Manifest validation failed ({p}): {exc}") from exc

    # -- Query helpers ------------------------------------------------------

    def get(self, name: str) -> WeightsEntry:
        """Return the manifest entry for ``name`` or raise :class:`ManifestError`."""

        try:
            return self.models[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.models)) or "<none>"
            raise ManifestError(
                f"No manifest entry named {name!r} (available: {available})"
            ) from exc

    def enabled_models(self) -> dict[str, WeightsEntry]:
        """Return only the entries with ``enabled: true``."""

        return {name: entry for name, entry in self.models.items() if entry.enabled}

    # -- Hashing ------------------------------------------------------------

    def manifest_hash(self) -> str:
        """SHA-256 of the canonical JSON serialization of the manifest.

        Stable across runs and platforms — two manifests that round-trip to
        the same pydantic state produce the same hash regardless of YAML
        key order or incidental whitespace.
        """

        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
