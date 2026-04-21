"""Celery tasks — real pipelines for Channels B & C (Stage-1/2 only on C).

Channel B (CAD / IFC uploads) shipped in Step 6 and is wired end-to-end
here: :func:`process_cad_file` drives :class:`src.parsers.dxf_parser.DXFParser`
or :class:`src.parsers.ifc_parser.IFCParser`, hands the parsed payload to
:class:`src.core.cad_graph_builder.CadGraphBuilder`, and returns the
validated :class:`BuildingGraph` via the task result backend.

Channel C (floor-plan images) lands Stage 1 + Stage 2 in Step 7:

* **Stage 1** (:mod:`src.cv.preprocessor`) normalises orientation /
  DPI / size for a round-trip to Claude vision.
* **Stage 2** (:mod:`src.cv.building_type_classifier`) asks the VLM to
  classify the plan into a :class:`BuildingType`; the output drives
  weights-manifest selection
  (:meth:`backend.weights.loader.WeightsLoader.select_slot_for_building_type`).

Stages 3+ (the actual detectors) still emit the Step-5 synthetic
scaffold, marked as such in the returned payload (``stub: True``,
``stage_completed: "stage_2_vlm_classification"``).  That scaffold
disappears in Step 9 once the real detectors are wired in.

Channel B failure modes are explicit:

*   ``DXF`` / ``IFC`` parse failure  → raise, Celery marks FAILURE, the
    API endpoint reconciles the async job record to ``failed`` with a
    structured error string.
*   ``DWG`` file without an ODA converter configured  → raise
    :class:`DWGUnsupportedError`; the endpoint surfaces it as a
    user-actionable failure rather than silently falling back to a
    stub (a silent stub in prod would be worse than a clear error).

The in-process twins (:func:`run_cad_inprocess`, :func:`run_cad_stub`,
:func:`run_floor_plan_stub`) exist for the endpoint's graceful
degradation path when Celery isn't importable or the broker is
unreachable — they return the same payload shape so the store
reconciliation logic doesn't branch on the transport.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import structlog

from src.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Channel B — real CAD / IFC pipeline
# ---------------------------------------------------------------------------


class DWGUnsupportedError(RuntimeError):
    """Raised when a DWG file lands without the ODA converter configured.

    Phase 1 depends on the Open Design Alliance File Converter for
    DWG→DXF conversion.  When it is not installed, we surface a clear,
    user-actionable error instead of fabricating a stub graph — a
    bogus-but-valid result is harder to debug than a loud failure.
    """


def _run_cad_pipeline(
    job_id: str, file_path: str, file_type: str
) -> dict[str, Any]:
    """Parse the CAD file and build a :class:`BuildingGraph`.

    Returns a payload shaped like the Celery task result so every
    caller (Celery worker, in-process fallback, tests) consumes the
    same contract.
    """

    from src.core.cad_graph_builder import CadGraphBuilder
    from src.schema.enums import InputSource

    key = file_type.upper()
    source_map = {
        "DXF": InputSource.DXF_FILE,
        "DWG": InputSource.DWG_FILE,
        "IFC": InputSource.IFC_FILE,
    }
    input_source = source_map.get(key)
    if input_source is None:
        raise ValueError(f"Unsupported CAD file type: {file_type!r}")

    resolved = Path(file_path)
    if not resolved.exists():
        raise FileNotFoundError(f"CAD source not found: {resolved}")

    if key == "IFC":
        from src.parsers.ifc_parser import IFCParser

        parsed = IFCParser().parse(resolved)
    elif key == "DXF":
        from src.parsers.dxf_parser import DXFParser

        parsed = DXFParser().parse(resolved)
    else:  # DWG
        parsed = _parse_dwg(resolved)

    graph = CadGraphBuilder().build(
        parsed, input_source=input_source, run_id=job_id, job_id=job_id
    )
    return {
        "status": "ok",
        "job_id": job_id,
        "channel": "cad",
        "file_type": key,
        "stub": False,
        "building_graph": _dump_graph(graph),
    }


def _parse_dwg(dwg_path: Path) -> dict[str, Any]:
    """Convert DWG → DXF via ODA, then parse the intermediate DXF.

    Raises :class:`DWGUnsupportedError` if the ODA converter is not
    available — that's the normal state in CI and on developer
    machines without the proprietary tool installed.

    The intermediate DXF file that ``DWGConverter`` writes next to the
    source (``dwg_path.with_suffix('.dxf')``) is deleted in a ``finally``
    block regardless of parse outcome so a worker processing many files
    does not silently accumulate ``.dxf`` siblings next to every upload.
    """

    from src.parsers.dwg_converter import DWGConversionError, DWGConverter
    from src.parsers.dxf_parser import DXFParser

    converter = DWGConverter()
    try:
        dxf_path = converter.convert(dwg_path)
    except DWGConversionError as exc:
        raise DWGUnsupportedError(
            "DWG parsing requires the ODA File Converter. "
            "Install it and set ``ODA_CONVERTER_PATH`` — see "
            "src.parsers.dwg_converter for details."
        ) from exc

    try:
        return DXFParser().parse(dxf_path)
    finally:
        # Best-effort cleanup.  A failure here (permission denied, file
        # already gone, etc.) must not mask a parse error or succeed
        # loudly — just log at debug so the worker keeps going.
        try:
            dxf_path.unlink(missing_ok=True)
        except OSError as cleanup_exc:  # pragma: no cover - platform dep.
            logger.debug(
                "dwg_intermediate_dxf_cleanup_failed",
                path=str(dxf_path),
                error=str(cleanup_exc),
            )


# ---------------------------------------------------------------------------
# Channel C — Stage 1 preprocessing + Stage 2 VLM classification
# (Stage 3+ detectors still emit the synthetic scaffold until Step 9)
# ---------------------------------------------------------------------------


def _run_image_pipeline(job_id: str, image_path: str) -> dict[str, Any]:
    """Run Channel C's Stages 1 and 2 against a floor-plan image.

    Steps:

    1. Stage 1: normalise the image for a multimodal-LLM round-trip
       (``Preprocessor.prepare_for_vlm``).
    2. Stage 2: classify the plan's ``BuildingType`` via Claude vision
       (``BuildingTypeClassifier.classify``); graceful fallback when no
       API key is configured keeps CI green.
    3. Use the classified type to pick a manifest slot (advisory — the
       Stage-3 detectors arrive in Step 9, but the slot is recorded on
       the graph so the reviewer can see which model *would* have run).
    4. Build the synthetic Stage-3 scaffold and overlay the VLM
       decision on ``metadata.inferred_building_type``; record the
       classification + selected slot as ``AssumptionRecord`` entries
       so the ``POST /review`` endpoint can override them.

    Returns the Celery-task payload shape
    (``status``, ``job_id``, ``channel``, ``stub``, ``building_graph``)
    plus Step-7 extensions (``classification``, ``selected_slot``,
    ``stage_completed``) for the endpoint to surface.
    """

    from src.config import settings
    from src.cv.building_type_classifier import BuildingTypeClassifier
    from src.cv.preprocessor import Preprocessor
    from src.schema.assumptions import AssumptionRecord
    from src.schema.enums import DetectorSource, InputSource
    from src.utils.completeness_scorer import annotate_with_completeness

    resolved = Path(image_path)
    if not resolved.exists():
        raise FileNotFoundError(f"image file not found: {resolved}")

    # --- Stage 1 -------------------------------------------------------
    vlm_payload = Preprocessor().prepare_for_vlm(resolved)

    # --- Stage 2 -------------------------------------------------------
    classifier = BuildingTypeClassifier(api_key=settings.anthropic_api_key)
    classification = classifier.classify(vlm_payload.png_bytes)

    # --- Manifest slot selection (advisory for Step 7) ----------------
    selected_slot = _select_wall_segmenter_slot(classification.building_type)

    # --- Stage 3+ scaffold (synthetic until Step 9) -------------------
    graph = _build_synthetic_graph(
        job_id,
        input_source=InputSource.FLOOR_PLAN_IMAGE,
        source_detector=DetectorSource.HEURISTIC,
    )

    # Overlay VLM output on the metadata.  A fallback classification
    # (no API key, parse failure, etc.) leaves the occupancy-derived
    # value that ``_build_synthetic_graph`` already set.
    if not classification.is_fallback:
        graph.metadata.inferred_building_type = classification.building_type

    register = graph.metadata.assumption_register
    register.append(
        AssumptionRecord.quick(
            id="channel_c_vlm_building_type",
            name="VLM-inferred building type",
            value=classification.building_type.value,
            source="src.cv.building_type_classifier",
            rationale=(
                classification.rationale
                if not classification.is_fallback
                else "VLM unavailable — falling back to occupancy-derived "
                "building type.  Override if the classification is wrong."
            ),
            confidence=classification.confidence,
            overrideable=True,
            affects_modules=[
                "weights_manifest_selection",
                "phase3.design",
            ],
        )
    )
    register.append(
        AssumptionRecord.quick(
            id="channel_c_vlm_image_preprocess",
            name="VLM image preprocessing",
            value={
                "encoded_width": vlm_payload.width,
                "encoded_height": vlm_payload.height,
                "original_width": vlm_payload.original_width,
                "original_height": vlm_payload.original_height,
                "dpi": vlm_payload.dpi,
                "dpi_source": vlm_payload.dpi_source,
                "was_rotated": vlm_payload.was_rotated,
                "was_downscaled": vlm_payload.was_downscaled,
            },
            source="src.cv.preprocessor.prepare_for_vlm",
            rationale=(
                "Image normalised for VLM round-trip: EXIF orientation "
                "applied, downscaled to ≤1568 px longest edge, PNG-encoded "
                "under Claude's 5 MB ceiling."
            ),
            confidence=1.0,
            overrideable=False,
            affects_modules=["channel_c.stage_1"],
        )
    )
    if selected_slot is not None:
        register.append(
            AssumptionRecord.quick(
                id="channel_c_wall_segmenter_slot",
                name="Selected wall-segmenter slot",
                value=selected_slot,
                source="backend.weights.loader",
                rationale=(
                    f"Slot resolved via kind=wall_segmenter + "
                    f"building_type={classification.building_type.value}. "
                    "Stage-3 detector will consume this slot in Step 9; "
                    "until then the wall list is the synthetic scaffold."
                ),
                confidence=1.0,
                overrideable=False,
                affects_modules=["stage3.wall_segmentation"],
            )
        )

    # Completeness must be recomputed now that we mutated the register.
    graph = annotate_with_completeness(graph)

    return {
        "status": "ok",
        "job_id": job_id,
        "channel": "image",
        "stub": True,  # Stage 3+ detectors still synthetic (Step 9 lands them)
        "stage_completed": "stage_2_vlm_classification",
        "classification": {
            "building_type": classification.building_type.value,
            "confidence": classification.confidence,
            "model_id": classification.model_id,
            "rationale": classification.rationale,
            "is_fallback": classification.is_fallback,
        },
        "selected_slot": selected_slot,
        "building_graph": _dump_graph(graph),
    }


def _select_wall_segmenter_slot(building_type) -> Optional[str]:
    """Resolve the ``wall_segmenter`` slot for *building_type*.

    Keeps the loader import + exception handling out of the hot path in
    :func:`_run_image_pipeline`.  Any failure to load the manifest
    (missing YAML, environment mis-configuration) is logged at warning
    level and treated as "no slot selected" — Channel C's Stage 2 is
    still useful even if Stage 3 can't be staged yet.
    """

    try:
        from backend.weights.loader import WeightsLoader

        loader = WeightsLoader.from_env()
        return loader.select_slot_for_building_type(
            kind="wall_segmenter", building_type=building_type
        )
    except Exception as exc:  # manifest load errors, settings issues, …
        logger.warning(
            "manifest_slot_selection_failed",
            building_type=getattr(building_type, "value", building_type),
            error=str(exc),
        )
        return None


# ---------------------------------------------------------------------------
# Channel C — synthetic stub (replaced in Step 9 by the real CV pipeline)
# ---------------------------------------------------------------------------


def _canonical_request():
    """Fixed request that drives every Channel-C stub.

    Kept deliberately minimal: six-by-five grid, three stories, office
    occupancy.  Callers relabel ``input_source`` and per-element
    provenance after building so the reviewer can distinguish stub
    output from a real detector run.
    """

    from src.schema.building_graph import Location
    from src.schema.enums import MaterialPreference, OccupancyType, RoofType
    from src.schema.input_models import StructuredInputRequest

    return StructuredInputRequest(
        project_name="synthetic-stub",
        location=Location(lat=0.0, lng=0.0, city="N/A", country="N/A"),
        length_mm=30000,
        width_mm=20000,
        num_stories=3,
        floor_to_floor_mm=3900,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        roof_type=RoofType.FLAT,
    )


def _build_synthetic_graph(job_id: str, *, input_source, source_detector):
    """Build, relabel, and re-score a synthetic :class:`BuildingGraph`.

    Every wall / room / column / core in the returned graph carries
    ``provenance.detector_source == source_detector`` with
    ``confidence_from_model=0.0`` — a loud signal to any reviewer that
    these elements are placeholders, not real detections.
    """

    from src.core.graph_builder import GraphBuilder
    from src.utils.completeness_scorer import annotate_with_completeness

    builder = GraphBuilder()
    graph = builder.from_structured_input(
        _canonical_request(), run_id=job_id, job_id=job_id
    )
    graph.metadata.input_source = input_source

    for collection in (graph.walls, graph.rooms, graph.column_candidates, graph.cores):
        for element in collection:
            prov = getattr(element, "provenance", None)
            if prov is None:
                continue
            prov.detector_source = source_detector
            prov.confidence_from_model = 0.0

    return annotate_with_completeness(graph)


def _dump_graph(graph) -> dict[str, Any]:
    """Serialise a BuildingGraph to a JSON-safe dict for Celery results."""

    return graph.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Celery tasks (registered only when Celery is importable)
# ---------------------------------------------------------------------------


if celery_app is not None:

    @celery_app.task(bind=True, name="civil_agent.process_floor_plan")
    def process_floor_plan(self, job_id: str, image_path: str) -> dict[str, Any]:
        """Channel-C task: Stage 1 preprocess + Stage 2 VLM classification.

        Stage 3+ (real detectors) arrive in Step 9; until then the
        returned graph is still the synthetic scaffold with VLM-driven
        ``metadata.inferred_building_type``.
        """

        logger.info(
            "process_floor_plan_start",
            task_id=self.request.id,
            job_id=job_id,
            image_path=image_path,
        )
        t0 = time.perf_counter()
        try:
            result = _run_image_pipeline(job_id, image_path)
            logger.info(
                "process_floor_plan_complete",
                task_id=self.request.id,
                job_id=job_id,
                classification=result["classification"]["building_type"],
                selected_slot=result["selected_slot"],
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return result
        except Exception as exc:
            logger.error(
                "process_floor_plan_failed",
                task_id=self.request.id,
                job_id=job_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    @celery_app.task(bind=True, name="civil_agent.process_cad_file")
    def process_cad_file(
        self, job_id: str, file_path: str, file_type: str
    ) -> dict[str, Any]:
        """Channel-B task: parse DXF / DWG / IFC and emit a BuildingGraph."""

        logger.info(
            "process_cad_file_start",
            task_id=self.request.id,
            job_id=job_id,
            file_path=file_path,
            file_type=file_type,
        )
        t0 = time.perf_counter()
        try:
            result = _run_cad_pipeline(job_id, file_path, file_type)
            logger.info(
                "process_cad_file_complete",
                task_id=self.request.id,
                job_id=job_id,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return result
        except Exception as exc:
            logger.error(
                "process_cad_file_failed",
                task_id=self.request.id,
                job_id=job_id,
                file_type=file_type,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

else:  # pragma: no cover — Celery not installed
    process_floor_plan = None  # type: ignore[assignment]
    process_cad_file = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# In-process fallbacks (used by tests and by the graceful-degradation path
# in the endpoints when Celery isn't importable / broker is down).
# ---------------------------------------------------------------------------


def run_image_inprocess(job_id: str, image_path: str) -> dict[str, Any]:
    """Synchronous twin of :func:`process_floor_plan` — runs the real
    Stage-1/Stage-2 pipeline.

    Used by the ``/image`` endpoint when Celery can't be reached so the
    user still gets a VLM-classified :class:`BuildingGraph` back inside
    the HTTP response — at the cost of running the classification
    inline on the API process.  Acceptable for one-off uploads;
    production should always have a healthy worker.
    """

    return _run_image_pipeline(job_id, image_path)


def run_floor_plan_stub(
    job_id: str, image_path: Optional[str] = None
) -> dict[str, Any]:
    """Synthetic Channel-C payload — kept for legacy tests that don't
    supply a real image path.

    Unlike :func:`run_image_inprocess`, this never touches the
    filesystem and always returns the fixed synthetic graph (no
    Stage-1/Stage-2).  Production endpoints route through
    :func:`run_image_inprocess` instead.
    """

    from src.schema.enums import DetectorSource, InputSource

    graph = _build_synthetic_graph(
        job_id,
        input_source=InputSource.FLOOR_PLAN_IMAGE,
        source_detector=DetectorSource.HEURISTIC,
    )
    return {
        "status": "ok",
        "job_id": job_id,
        "channel": "image",
        "stub": True,
        "building_graph": _dump_graph(graph),
    }


def run_cad_inprocess(
    job_id: str, file_path: str, file_type: str
) -> dict[str, Any]:
    """Synchronous twin of :func:`process_cad_file` — runs the real pipeline.

    Used by the ``/cad`` endpoint when Celery can't be reached so the
    user still gets a real :class:`BuildingGraph` back inside the
    HTTP response — at the cost of running the parse inline on the API
    process.  Acceptable fallback for small DXFs; production should
    always have a healthy worker.
    """

    return _run_cad_pipeline(job_id, file_path, file_type)


def run_cad_stub(
    job_id: str, file_path: Optional[str] = None, file_type: str = "DXF"
) -> dict[str, Any]:
    """Synthetic Channel-B payload — kept for Step-5 compatibility tests.

    Unlike :func:`run_cad_inprocess`, this never touches the filesystem
    and always returns the fixed synthetic graph.  The endpoint does
    *not* route production traffic here; only the pre-Step-6 tests
    (and any reviewer who wants a deterministic payload) should call
    it.
    """

    from src.schema.enums import DetectorSource, InputSource

    source_map = {
        "DXF": (InputSource.DXF_FILE, DetectorSource.CAD_DIRECT),
        "DWG": (InputSource.DWG_FILE, DetectorSource.CAD_DIRECT),
        "IFC": (InputSource.IFC_FILE, DetectorSource.IFC_DIRECT),
    }
    input_source, source_detector = source_map.get(
        file_type.upper(), (InputSource.DXF_FILE, DetectorSource.CAD_DIRECT)
    )
    graph = _build_synthetic_graph(
        job_id,
        input_source=input_source,
        source_detector=source_detector,
    )
    return {
        "status": "ok",
        "job_id": job_id,
        "channel": "cad",
        "file_type": file_type.upper(),
        "stub": True,
        "building_graph": _dump_graph(graph),
    }


__all__ = [
    "DWGUnsupportedError",
    "_build_synthetic_graph",
    "_run_cad_pipeline",
    "_run_image_pipeline",
    "process_cad_file",
    "process_floor_plan",
    "run_cad_inprocess",
    "run_cad_stub",
    "run_floor_plan_stub",
    "run_image_inprocess",
]
