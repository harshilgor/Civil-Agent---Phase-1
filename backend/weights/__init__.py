"""Public surface of the weights package — the manifest-driven loader.

All Phase 1 call sites should go through :class:`WeightsLoader` (typically
via :meth:`WeightsLoader.from_env`) rather than touching the manifest /
backend modules directly.
"""

from .backends import (
    LocalWeightsBackend,
    S3WeightsBackend,
    WeightsBackend,
    WeightsBackendError,
    get_backend,
    sha256_of_file,
)
from .loader import (
    ResolvedWeights,
    WeightsLoader,
    WeightsLoaderError,
)
from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    Architecture,
    ManifestError,
    WeightsEntry,
    WeightsManifest,
    WeightsSource,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "Architecture",
    "LocalWeightsBackend",
    "ManifestError",
    "ResolvedWeights",
    "S3WeightsBackend",
    "WeightsBackend",
    "WeightsBackendError",
    "WeightsEntry",
    "WeightsLoader",
    "WeightsLoaderError",
    "WeightsManifest",
    "WeightsSource",
    "get_backend",
    "sha256_of_file",
]
