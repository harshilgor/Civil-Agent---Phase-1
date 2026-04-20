"""High-level weights loader.

Consumers ask the loader for a named slot (``"wall_segmenter_residential"``,
``"yolo_wall_seg"`` …) and get back either a :class:`ResolvedWeights` handle
(file path + metadata + provenance helper) or, when they ask for it, a ready
``torch.nn.Module`` instance produced by the architecture-specific code path.

Two hard rules:

* **Lazy heavy imports.**  ``torch`` / ``segmentation_models_pytorch`` /
  ``ultralytics`` are only imported inside :meth:`WeightsLoader.build_model`,
  so Phase 1 API-gateway containers that never instantiate models pay zero
  runtime cost for them.

* **Disabled slots never throw.**  Per the Step 1 Q&A, optional detectors
  (YOLO-Seg, symbol detector) must silently disengage when their manifest
  entries carry ``enabled: false`` or are absent.  Callers that need a model
  use :meth:`WeightsLoader.get_if_enabled` which returns ``None`` in that
  case; callers that insist on a specific slot use :meth:`resolve`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.schema.enums import DetectorSource
from src.schema.provenance import ProvenanceRecord

from .backends import WeightsBackend, WeightsBackendError, get_backend
from .manifest import (
    Architecture,
    ManifestError,
    WeightsEntry,
    WeightsManifest,
)


class WeightsLoaderError(RuntimeError):
    """Raised on a loader-level problem (missing slot, unknown architecture)."""


# ---------------------------------------------------------------------------
# ResolvedWeights — the handle every downstream consumer should carry.
# ---------------------------------------------------------------------------


# Architecture → DetectorSource mapping used when building a ProvenanceRecord
# without an explicit override.  Kept here (not on the enum) so that the
# ``src.schema`` layer stays ignorant of the perception concretions.
_DEFAULT_DETECTOR_SOURCE: dict[Architecture, DetectorSource] = {
    Architecture.CUBICASA_HG: DetectorSource.CUBICASA_HG,
    Architecture.SMP_UNET: DetectorSource.SMP_UNET,
    Architecture.YOLOV8_SEG: DetectorSource.YOLO_SEG,
    Architecture.YOLOV8: DetectorSource.SYMBOL_DETECTOR,
}


@dataclass(frozen=True)
class ResolvedWeights:
    """A materialised weights handle: file on disk + manifest metadata."""

    name: str
    entry: WeightsEntry
    path: Path
    manifest_hash: str

    # -- pass-throughs that read nicer than ``.entry.xxx`` ------------------

    @property
    def architecture(self) -> Architecture:
        return self.entry.architecture

    @property
    def model_id(self) -> str:
        return self.entry.model_id

    @property
    def model_version(self) -> str:
        return self.entry.model_version

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.entry.params)  # defensive copy

    @property
    def num_classes(self) -> Optional[int]:
        return self.entry.num_classes

    # -- Provenance helper --------------------------------------------------

    def to_provenance(
        self,
        *,
        run_id: Optional[str] = None,
        confidence_from_model: Optional[float] = None,
        detector_source: Optional[DetectorSource] = None,
        notes: Optional[str] = None,
    ) -> ProvenanceRecord:
        """Build a :class:`ProvenanceRecord` pre-populated from this handle.

        Any element produced using these weights should carry the resulting
        record on its ``.provenance`` field — that is the only auditable
        link between an emitted wall/room polygon and the weights manifest
        revision that produced it.
        """

        return ProvenanceRecord(
            detector_source=detector_source
            or _DEFAULT_DETECTOR_SOURCE[self.architecture],
            model_id=self.model_id,
            model_version=self.model_version,
            weights_manifest_hash=self.manifest_hash,
            run_id=run_id,
            confidence_from_model=confidence_from_model,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# WeightsLoader
# ---------------------------------------------------------------------------


class WeightsLoader:
    """Resolves manifest slots to :class:`ResolvedWeights` and (lazily) models.

    Typical wiring:

        loader = WeightsLoader.from_env()            # uses settings + manifest file
        rw = loader.get_if_enabled("yolo_wall_seg")  # None when disabled/missing
        if rw is not None:
            model = loader.build_model("yolo_wall_seg")
    """

    def __init__(self, manifest: WeightsManifest, backend: WeightsBackend) -> None:
        self.manifest = manifest
        self.backend = backend
        self._manifest_hash = manifest.manifest_hash()

    # -- Construction -------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        manifest_path: str | Path | None = None,
        *,
        backend: WeightsBackend | None = None,
    ) -> "WeightsLoader":
        """Construct a loader using :class:`~src.config.Settings`."""

        from src.config import settings  # noqa: PLC0415

        path = Path(manifest_path) if manifest_path else Path(settings.weights_manifest_path)
        manifest = WeightsManifest.load(path)
        return cls(manifest=manifest, backend=backend or get_backend())

    # -- Introspection ------------------------------------------------------

    def is_known(self, name: str) -> bool:
        return name in self.manifest.models

    def is_enabled(self, name: str) -> bool:
        entry = self.manifest.models.get(name)
        return entry is not None and entry.enabled

    def is_available(self, name: str) -> bool:
        """True when the slot is enabled *and* the backend can fetch it."""

        entry = self.manifest.models.get(name)
        if entry is None or not entry.enabled:
            return False
        try:
            return self.backend.available(entry)
        except WeightsBackendError:
            return False

    @property
    def manifest_hash(self) -> str:
        return self._manifest_hash

    # -- Core resolve -------------------------------------------------------

    def resolve(self, name: str) -> ResolvedWeights:
        """Fetch-and-verify a required slot; raise on any failure."""

        try:
            entry = self.manifest.get(name)
        except ManifestError as exc:
            raise WeightsLoaderError(str(exc)) from exc
        if not entry.enabled:
            raise WeightsLoaderError(
                f"Manifest entry {name!r} is disabled; use get_if_enabled() "
                "if this stage is optional."
            )
        try:
            path = self.backend.fetch(entry)
        except WeightsBackendError as exc:
            raise WeightsLoaderError(
                f"Could not fetch weights for {name!r}: {exc}"
            ) from exc
        return ResolvedWeights(
            name=name,
            entry=entry,
            path=path.resolve(),
            manifest_hash=self._manifest_hash,
        )

    def get_if_enabled(self, name: str) -> Optional[ResolvedWeights]:
        """Return :class:`ResolvedWeights` or ``None`` for disabled/missing slots.

        Used by optional detectors (YOLO-Seg, symbol detector) whose absence
        must only ding the completeness score, never abort the pipeline.
        """

        if not self.is_enabled(name):
            return None
        try:
            return self.resolve(name)
        except WeightsLoaderError:
            return None

    # -- Model construction (lazy heavy imports) ---------------------------

    def build_model(self, name: str) -> Any:
        """Resolve the slot and return an instantiated model object.

        The return type is intentionally ``Any`` because each architecture
        yields a different concrete class (``torch.nn.Module`` for the
        hourglass / U-Net paths, ``ultralytics.YOLO`` for YOLO).  Callers
        that need a strict type should check ``resolved.architecture``.
        """

        resolved = self.resolve(name)
        arch = resolved.architecture
        if arch is Architecture.CUBICASA_HG:
            return _build_cubicasa_hg(resolved)
        if arch is Architecture.SMP_UNET:
            return _build_smp_unet(resolved)
        if arch is Architecture.YOLOV8_SEG:
            return _build_ultralytics(resolved)
        if arch is Architecture.YOLOV8:
            return _build_ultralytics(resolved)
        raise WeightsLoaderError(f"Unsupported architecture: {arch}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Architecture builders — lazy imports so pure-Phase-1 installs stay thin.
# ---------------------------------------------------------------------------


def _require(module_name: str, extras_hint: str) -> Any:
    try:
        import importlib  # noqa: PLC0415

        return importlib.import_module(module_name)
    except ImportError as exc:
        raise WeightsLoaderError(
            f"Missing runtime dependency {module_name!r}. "
            f"Install the '{extras_hint}' extra: `pip install .[{extras_hint}]`."
        ) from exc


def _build_cubicasa_hg(resolved: ResolvedWeights) -> Any:
    """Instantiate the legacy CubiCasa hourglass and load its checkpoint.

    Reproduces the head-resizing dance from the original vendor adapter.
    The vendor code lives under ``vendors/cubicasa/floortrans`` and is
    imported dynamically so Phase 1 boxes without the vendor tree can still
    execute the other code paths.
    """

    torch = _require("torch", "ml")
    # Ensure the vendor tree is importable; reuse the existing helper.
    from backend.pipeline.stage1_perception.load_utils import (  # noqa: PLC0415
        ModelLoadError,
        resolve_module,
    )

    resolve_module(
        vendor_path="vendors/cubicasa",
        local_module_candidates=("floortrans.models.hg_furukawa_original",),
        external_module_candidates=("floortrans.models.hg_furukawa_original",),
    )
    model_module = __import__(
        "floortrans.models.hg_furukawa_original",
        fromlist=["hg_furukawa_original"],
    )
    builder = getattr(model_module, "hg_furukawa_original", None)
    if builder is None:
        raise WeightsLoaderError(
            "vendors/cubicasa does not expose hg_furukawa_original()"
        )

    params = resolved.params
    bootstrap_classes = int(params.get("bootstrap_n_classes", 51))
    n_classes = int(resolved.num_classes or params.get("num_classes", 44))

    model = builder(n_classes=bootstrap_classes)
    model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(
        n_classes, n_classes, kernel_size=4, stride=4
    )

    checkpoint = torch.load(str(resolved.path), map_location="cpu", weights_only=False)
    if isinstance(checkpoint, dict) and "model_state" in checkpoint:
        state = checkpoint["model_state"]
    elif isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state = checkpoint["state_dict"]
    else:
        state = checkpoint
    try:
        model.load_state_dict(state)
    except Exception as exc:  # pragma: no cover  (exercised only with real weights)
        raise ModelLoadError(
            f"Failed to load CubiCasa state_dict from {resolved.path}: {exc}"
        ) from exc
    model.eval()
    return model


def _build_smp_unet(resolved: ResolvedWeights) -> Any:
    """Instantiate ``segmentation_models_pytorch.Unet`` and load weights."""

    torch = _require("torch", "ml")
    smp = _require("segmentation_models_pytorch", "ml")

    params = resolved.params
    encoder_name = str(params.get("encoder_name", "resnet34"))
    encoder_weights = params.get("encoder_weights")  # may be None
    in_channels = int(params.get("in_channels", 3))
    classes = int(resolved.num_classes or params.get("classes", 7))

    model = smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=encoder_weights,
        in_channels=in_channels,
        classes=classes,
    )
    state = torch.load(str(resolved.path), map_location="cpu", weights_only=False)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    model.load_state_dict(state)
    model.eval()
    return model


def _build_ultralytics(resolved: ResolvedWeights) -> Any:
    """Instantiate an Ultralytics YOLO model (detection or segmentation)."""

    ultralytics = _require("ultralytics", "ml")
    return ultralytics.YOLO(str(resolved.path))
