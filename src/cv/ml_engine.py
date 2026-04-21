"""Step-8 ML engine — the façade Stage 3 talks to.

Responsibilities:

1. Resolve three manifest slots at run time, keyed on
   :class:`~src.schema.enums.BuildingType`:

   * ``wall_segmenter`` — the primary U-Net / CubiCasa HG.  Driven by
     Channel C's Stage-2 VLM classification; the right architecture for
     the inferred building type is picked from the manifest.
   * ``wall_fallback``  — a universal YOLO-Seg wall segmenter.  Only
     consulted when the primary fails (disabled, unfetchable, or
     below-threshold confidence).  Its absence is non-fatal — it only
     drops the completeness-scorer's ``detector_coverage``.
   * ``symbol_detector`` — a universal YOLOv8 detection model for
     doors / windows / stairs / elevators.  Optional in the same way.

2. Instantiate the corresponding adapter (see :mod:`.detector_adapters`)
   and stamp every produced artefact with a
   :class:`~src.schema.provenance.ProvenanceRecord` built from the
   resolved weights' manifest hash + ``model_id`` + ``model_version``.

3. Run the detectors on a BGR image and return typed results that
   Stage 9 (the detector-driven graph builder) can consume without
   caring which architecture produced them.

The engine deliberately does **not** preprocess the image itself.  The
:class:`~src.cv.preprocessor.Preprocessor` owns the Stage-3 pixel path
(``preprocess(path)["original"]``) at full resolution; the engine simply
consumes whatever array it is handed.  That split keeps the engine
trivially testable with ``np.ones((h, w, 3), dtype=np.uint8)`` fakes.

Testing seam: :class:`MLEngine` accepts injected adapter + provenance
pairs through :class:`ResolvedDetector` so integration tests can exercise
the primary / fallback / symbol pipelines with synthetic masks and
zero ``torch`` / ``ultralytics`` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import structlog

from backend.weights.loader import (
    ResolvedWeights,
    WeightsLoader,
    WeightsLoaderError,
)
from src.schema.enums import BuildingType, DetectorSource
from src.schema.provenance import ProvenanceRecord

from .detector_adapters import (
    SymbolDetection,
    SymbolDetectorAdapter,
    WallSegmentationOutput,
    WallSegmenterAdapter,
    build_symbol_adapter,
    build_wall_adapter,
)

logger = structlog.get_logger(__name__)


# Manifest ``kind`` values.  Kept as module constants so test code, the
# manifest loader, and future slot additions all reference the same
# strings.
KIND_WALL_PRIMARY = "wall_segmenter"
KIND_WALL_FALLBACK = "wall_fallback"
KIND_SYMBOL_DETECTOR = "symbol_detector"

# Engine-level fallback threshold used only when neither the caller nor
# the manifest sets one.  Declared a **placeholder** — the real tuning
# lives per-slot on the manifest's ``confidence_threshold`` field so
# different checkpoints (CubiCasa HG on residential CubiCasa5K vs. an
# SMP U-Net on the noisier MLStructFP corpus) can have their own
# operating points without any code change.  If you find yourself
# wanting to tune this constant, set it on the manifest instead.
DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD = 0.20


# ---------------------------------------------------------------------------
# Resolution bundles — what the engine carries internally
# ---------------------------------------------------------------------------


@dataclass
class ResolvedDetector:
    """A detector ready to run: adapter + provenance + its manifest slot.

    The engine holds one of these per slot.  Tests can construct the
    bundle directly to bypass manifest resolution; production code goes
    through :meth:`MLEngine.from_loader`.
    """

    slot: str
    adapter: Any  # WallSegmenterAdapter | SymbolDetectorAdapter
    provenance: ProvenanceRecord
    resolved: Optional[ResolvedWeights] = None


# ---------------------------------------------------------------------------
# Engine output types — what Stage 9 consumes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WallSegmentationResult:
    """Outcome of :meth:`MLEngine.segment_walls`.

    ``provenance`` is always present — either the primary's, the
    fallback's, or a synthetic stub that marks the run as
    "no detector available" (``detector_source = VLM_GAP_FILL`` with a
    zero confidence — a downstream consumer can always tell whether the
    mask came from a real model by inspecting
    ``detector_source`` + ``model_id``).
    """

    mask: np.ndarray
    element_masks: dict[str, np.ndarray]
    confidence: float
    provenance: ProvenanceRecord
    used_fallback: bool
    primary_slot: Optional[str]
    fallback_slot: Optional[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SymbolDetectionResult:
    """Outcome of :meth:`MLEngine.detect_symbols`.

    When the symbol detector is disabled or unresolvable, ``enabled`` is
    ``False`` and ``detections`` is empty.  Per the Phase-1 contract
    that absence dings the completeness score but never aborts a run.
    """

    detections: list[SymbolDetection]
    provenance: Optional[ProvenanceRecord]
    enabled: bool
    slot: Optional[str]
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MLEngine
# ---------------------------------------------------------------------------


class MLEngine:
    """Orchestrate wall segmentation + symbol detection from the manifest.

    Construct either:

    * **Through the loader** — :meth:`MLEngine.from_loader`.  Production
      wiring.  Resolves all three slots eagerly (so a missing slot is
      visible at worker start-up, not deep inside a background task)
      and instantiates the adapters.

    * **Through the constructor** — pass one or more
      :class:`ResolvedDetector` bundles directly.  Testing wiring.
      Bypasses manifest resolution entirely; useful for driving the
      engine with hand-crafted synthetic masks.
    """

    def __init__(
        self,
        *,
        building_type: BuildingType,
        run_id: Optional[str] = None,
        wall_primary: Optional[ResolvedDetector] = None,
        wall_fallback: Optional[ResolvedDetector] = None,
        symbol: Optional[ResolvedDetector] = None,
        confidence_threshold: float = DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._building_type = building_type
        self._run_id = run_id
        self._wall_primary = wall_primary
        self._wall_fallback = wall_fallback
        self._symbol = symbol
        self._confidence_threshold = float(confidence_threshold)

    # -- Properties (read-only introspection) ------------------------------

    @property
    def building_type(self) -> BuildingType:
        return self._building_type

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    @property
    def primary_slot(self) -> Optional[str]:
        return self._wall_primary.slot if self._wall_primary else None

    @property
    def fallback_slot(self) -> Optional[str]:
        return self._wall_fallback.slot if self._wall_fallback else None

    @property
    def symbol_slot(self) -> Optional[str]:
        return self._symbol.slot if self._symbol else None

    @property
    def has_primary_wall(self) -> bool:
        return self._wall_primary is not None

    @property
    def has_fallback_wall(self) -> bool:
        return self._wall_fallback is not None

    @property
    def has_symbol_detector(self) -> bool:
        return self._symbol is not None

    # -- Construction from a loader ----------------------------------------

    @classmethod
    def from_loader(
        cls,
        loader: WeightsLoader,
        *,
        building_type: BuildingType,
        run_id: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
    ) -> "MLEngine":
        """Resolve every slot against ``loader`` and return an MLEngine.

        Individual slot failures are logged and degrade gracefully —
        the engine carries ``None`` for that slot and the corresponding
        public property reports ``False``.

        Threshold resolution order (first match wins):

        1. The explicit ``confidence_threshold`` argument to this
           factory.  Production callers normally leave it unset.
        2. The primary slot's ``confidence_threshold`` on the manifest
           entry.  Per-checkpoint tuning lives here so the CubiCasa
           residential weights and a future SMP-U-Net commercial
           checkpoint can have independent operating points.
        3. :data:`DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD` as a
           last-resort placeholder.

        The only way this call can raise is if a loader-level
        invariant is violated (e.g. the manifest YAML itself is
        malformed), and in that case the exception bubbles up from
        :meth:`WeightsLoader.resolve`.
        """

        wall_primary = _resolve_wall_slot(
            loader,
            kind=KIND_WALL_PRIMARY,
            building_type=building_type,
            run_id=run_id,
        )
        wall_fallback = _resolve_wall_slot(
            loader,
            kind=KIND_WALL_FALLBACK,
            building_type=building_type,
            run_id=run_id,
        )
        symbol = _resolve_symbol_slot(
            loader,
            building_type=building_type,
            run_id=run_id,
        )

        resolved_threshold = _resolve_threshold(
            caller_threshold=confidence_threshold,
            primary=wall_primary,
        )
        return cls(
            building_type=building_type,
            run_id=run_id,
            wall_primary=wall_primary,
            wall_fallback=wall_fallback,
            symbol=symbol,
            confidence_threshold=resolved_threshold,
        )

    # -- Detection surface --------------------------------------------------

    def segment_walls(self, image: np.ndarray) -> WallSegmentationResult:
        """Run the primary wall segmenter, falling back on low-confidence or failure.

        Flow:

        1. If the primary is resolved, run it.  If it raises, treat the
           primary as unavailable for this call and drop through to (2).
        2. If the primary produced a below-threshold confidence, treat
           it as unreliable and drop through to (3).
        3. If the fallback is resolved, run it.  Its output replaces
           the primary's, the provenance switches to the fallback's,
           and a note records *why* the fallback engaged.
        4. If neither produces a mask, return an empty mask with a
           synthetic provenance so downstream consumers can distinguish
           "no detector ran" from "detector ran and returned nothing".
        """

        notes: list[str] = []

        primary_output: Optional[WallSegmentationOutput] = None
        primary_failed_msg: Optional[str] = None
        if self._wall_primary is not None:
            try:
                primary_output = _run_wall_adapter(
                    self._wall_primary.adapter, image
                )
            except Exception as exc:  # noqa: BLE001
                primary_failed_msg = (
                    f"primary wall segmenter raised: {type(exc).__name__}: {exc}"
                )
                logger.warning(
                    "ml_engine_primary_failed",
                    slot=self._wall_primary.slot,
                    error=str(exc),
                )
                notes.append(primary_failed_msg)
        else:
            notes.append(
                "no primary wall segmenter resolved from manifest "
                f"(building_type={self._building_type.value})"
            )

        # Decide whether to engage the fallback.
        engage_fallback = False
        if primary_output is None:
            engage_fallback = True
        elif primary_output.confidence < self._confidence_threshold:
            notes.append(
                f"primary confidence {primary_output.confidence:.3f} below "
                f"threshold {self._confidence_threshold:.3f}"
            )
            engage_fallback = True

        fallback_output: Optional[WallSegmentationOutput] = None
        if engage_fallback and self._wall_fallback is not None:
            try:
                fallback_output = _run_wall_adapter(
                    self._wall_fallback.adapter, image
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ml_engine_fallback_failed",
                    slot=self._wall_fallback.slot,
                    error=str(exc),
                )
                notes.append(
                    f"fallback wall segmenter raised: "
                    f"{type(exc).__name__}: {exc}"
                )

        return self._assemble_wall_result(
            primary_output=primary_output,
            fallback_output=fallback_output,
            image_shape=image.shape[:2],
            notes=notes,
        )

    def detect_symbols(self, image: np.ndarray) -> SymbolDetectionResult:
        """Run the symbol detector; return empty-but-structured result when disabled.

        Failures raise-through as warnings in ``notes`` and an empty
        detection list, matching the Phase-1 "optional detectors only
        ding the completeness score" contract.
        """

        if self._symbol is None:
            return SymbolDetectionResult(
                detections=[],
                provenance=None,
                enabled=False,
                slot=None,
                notes=[
                    "no symbol detector resolved from manifest "
                    f"(building_type={self._building_type.value})"
                ],
            )

        try:
            adapter: SymbolDetectorAdapter = self._symbol.adapter
            detections = adapter.detect(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ml_engine_symbol_failed",
                slot=self._symbol.slot,
                error=str(exc),
            )
            return SymbolDetectionResult(
                detections=[],
                provenance=self._symbol.provenance,
                enabled=True,
                slot=self._symbol.slot,
                notes=[
                    f"symbol detector raised: {type(exc).__name__}: {exc}"
                ],
            )

        logger.info(
            "ml_engine_symbols",
            slot=self._symbol.slot,
            count=len(detections),
        )
        return SymbolDetectionResult(
            detections=list(detections),
            provenance=self._symbol.provenance,
            enabled=True,
            slot=self._symbol.slot,
            notes=[],
        )

    # -- Internal helpers --------------------------------------------------

    def _assemble_wall_result(
        self,
        *,
        primary_output: Optional[WallSegmentationOutput],
        fallback_output: Optional[WallSegmentationOutput],
        image_shape: tuple[int, int],
        notes: list[str],
    ) -> WallSegmentationResult:
        # Pick the output that will drive the returned mask + provenance.
        chosen_output: Optional[WallSegmentationOutput] = None
        chosen_prov: Optional[ProvenanceRecord] = None
        used_fallback = False

        if fallback_output is not None:
            chosen_output = fallback_output
            if self._wall_fallback is not None:
                chosen_prov = self._wall_fallback.provenance.model_copy(
                    update={"confidence_from_model": fallback_output.confidence}
                )
            used_fallback = True
        elif primary_output is not None:
            chosen_output = primary_output
            if self._wall_primary is not None:
                chosen_prov = self._wall_primary.provenance.model_copy(
                    update={"confidence_from_model": primary_output.confidence}
                )

        if chosen_output is not None and chosen_prov is not None:
            return WallSegmentationResult(
                mask=chosen_output.wall_mask,
                element_masks=dict(chosen_output.element_masks),
                confidence=chosen_output.confidence,
                provenance=chosen_prov,
                used_fallback=used_fallback,
                primary_slot=self.primary_slot,
                fallback_slot=self.fallback_slot,
                notes=list(notes),
            )

        # No detector produced anything — emit a structured stub.
        notes.append(
            "no wall segmenter was available; returning empty mask"
        )
        h, w = image_shape
        empty = np.zeros((h, w), dtype=np.uint8)
        stub_prov = ProvenanceRecord(
            detector_source=DetectorSource.VLM_GAP_FILL,
            model_id="ml_engine_stub",
            model_version="0.0.0",
            run_id=self._run_id,
            confidence_from_model=0.0,
            notes="no wall segmenter available",
        )
        return WallSegmentationResult(
            mask=empty,
            element_masks={},
            confidence=0.0,
            provenance=stub_prov,
            used_fallback=False,
            primary_slot=self.primary_slot,
            fallback_slot=self.fallback_slot,
            notes=list(notes),
        )


# ---------------------------------------------------------------------------
# Private helpers — kept module-level so from_loader() stays flat and the
# same code paths are exercised from tests that drive resolution directly.
# ---------------------------------------------------------------------------


def _run_wall_adapter(
    adapter: WallSegmenterAdapter, image: np.ndarray
) -> WallSegmentationOutput:
    return adapter.segment(image)


def _resolve_threshold(
    *,
    caller_threshold: Optional[float],
    primary: Optional[ResolvedDetector],
) -> float:
    """Pick the primary-vs-fallback threshold.

    Resolution order matches the :meth:`MLEngine.from_loader` docstring:
    caller-supplied override → manifest entry on the primary slot →
    the engine-level placeholder default.
    """

    if caller_threshold is not None:
        return float(caller_threshold)
    if (
        primary is not None
        and primary.resolved is not None
        and primary.resolved.entry.confidence_threshold is not None
    ):
        return float(primary.resolved.entry.confidence_threshold)
    return DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD


def _resolve_wall_slot(
    loader: WeightsLoader,
    *,
    kind: str,
    building_type: BuildingType,
    run_id: Optional[str],
) -> Optional[ResolvedDetector]:
    """Resolve a ``wall_segmenter`` / ``wall_fallback`` slot and build its adapter.

    Returns ``None`` on any failure along the chain:

    * No slot matches ``(kind, building_type)`` in the manifest.
    * The backend cannot fetch the artefact.
    * :func:`build_model` fails (missing torch, checkpoint on disk is
      corrupt, etc.).

    The loader already logs every failure at warning level, so this
    function only needs to swallow the exception and return ``None``.
    """

    slot = loader.select_slot_for_building_type(
        kind=kind, building_type=building_type
    )
    if slot is None:
        return None
    try:
        resolved = loader.resolve(slot)
    except WeightsLoaderError as exc:
        logger.warning(
            "ml_engine_slot_fetch_failed",
            slot=slot,
            kind=kind,
            error=str(exc),
        )
        return None

    # Build the model — lazy imports happen here.  A missing torch /
    # ultralytics or a corrupt checkpoint is non-fatal for optional
    # slots; for the primary it still surfaces as "no primary
    # resolved" and the fallback (or the empty-mask stub) takes over.
    try:
        model = loader.build_model(slot)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ml_engine_build_model_failed",
            slot=slot,
            kind=kind,
            error=str(exc),
        )
        return None

    try:
        split_prediction = (
            _load_cubicasa_split_prediction() if kind == KIND_WALL_PRIMARY
            and resolved.architecture.value == "cubicasa_hg" else None
        )
        adapter = build_wall_adapter(
            resolved, model, split_prediction=split_prediction
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ml_engine_adapter_build_failed",
            slot=slot,
            kind=kind,
            error=str(exc),
        )
        return None

    provenance = resolved.to_provenance(run_id=run_id)
    return ResolvedDetector(
        slot=slot, adapter=adapter, provenance=provenance, resolved=resolved
    )


def _resolve_symbol_slot(
    loader: WeightsLoader,
    *,
    building_type: BuildingType,
    run_id: Optional[str],
) -> Optional[ResolvedDetector]:
    """Same contract as :func:`_resolve_wall_slot` for symbol detectors."""

    slot = loader.select_slot_for_building_type(
        kind=KIND_SYMBOL_DETECTOR, building_type=building_type
    )
    if slot is None:
        return None
    try:
        resolved = loader.resolve(slot)
    except WeightsLoaderError as exc:
        logger.warning(
            "ml_engine_symbol_fetch_failed", slot=slot, error=str(exc)
        )
        return None
    try:
        model = loader.build_model(slot)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ml_engine_symbol_build_failed", slot=slot, error=str(exc)
        )
        return None
    try:
        adapter = build_symbol_adapter(resolved, model)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ml_engine_symbol_adapter_failed", slot=slot, error=str(exc)
        )
        return None
    provenance = resolved.to_provenance(run_id=run_id)
    return ResolvedDetector(
        slot=slot, adapter=adapter, provenance=provenance, resolved=resolved
    )


def _load_cubicasa_split_prediction() -> Any:
    """Import ``floortrans.post_prosessing.split_prediction`` lazily.

    Kept in a helper so the engine module itself does not import the
    vendor tree.  Raises :class:`ImportError` if the vendor tree is
    absent — callers upstream swallow that as "adapter unavailable".
    """

    # Ensure the vendor path is on sys.path; reuse the same helper the
    # loader uses so the resolution rules match.
    from backend.pipeline.stage1_perception.load_utils import (  # noqa: PLC0415
        resolve_module,
    )

    resolve_module(
        vendor_path="vendors/cubicasa",
        local_module_candidates=("floortrans.post_prosessing",),
        external_module_candidates=("floortrans.post_prosessing",),
    )
    post_module = __import__(
        "floortrans.post_prosessing",
        fromlist=["split_prediction"],
    )
    return post_module.split_prediction


__all__ = [
    "KIND_WALL_PRIMARY",
    "KIND_WALL_FALLBACK",
    "KIND_SYMBOL_DETECTOR",
    "DEFAULT_PRIMARY_CONFIDENCE_THRESHOLD",
    "MLEngine",
    "ResolvedDetector",
    "WallSegmentationResult",
    "SymbolDetectionResult",
]
