"""Celery tasks — Step-5 stubs for Channel C, **real pipeline** for Channel B.

Channel B (CAD / IFC uploads) lands in Step 6 and is wired end-to-end
here: :func:`process_cad_file` drives :class:`src.parsers.dxf_parser.DXFParser`
or :class:`src.parsers.ifc_parser.IFCParser`, hands the parsed payload to
:class:`src.core.cad_graph_builder.CadGraphBuilder`, and returns the
validated :class:`BuildingGraph` via the task result backend.

Channel C (floor-plan images) is still a synthetic stub — the real CV
pipeline arrives in Step 9.  The stub is preserved so the async plumbing
end-to-end tests keep running until the detectors slot in behind the
same task name (``civil_agent.process_floor_plan``).

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
    """

    from src.parsers.dwg_converter import DWGConverter, DWGConversionError
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

    return DXFParser().parse(dxf_path)


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
        """Stub Channel-C task: pretend to run the CV pipeline."""

        from src.schema.enums import DetectorSource, InputSource

        logger.info(
            "stub_process_floor_plan_start",
            task_id=self.request.id,
            job_id=job_id,
            image_path=image_path,
        )
        t0 = time.perf_counter()
        try:
            graph = _build_synthetic_graph(
                job_id,
                input_source=InputSource.FLOOR_PLAN_IMAGE,
                source_detector=DetectorSource.HEURISTIC,
            )
            payload = _dump_graph(graph)
            logger.info(
                "stub_process_floor_plan_complete",
                task_id=self.request.id,
                job_id=job_id,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return {
                "status": "ok",
                "job_id": job_id,
                "channel": "image",
                "stub": True,
                "building_graph": payload,
            }
        except Exception as exc:
            logger.error(
                "stub_process_floor_plan_failed",
                task_id=self.request.id,
                job_id=job_id,
                error=str(exc),
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


def run_floor_plan_stub(job_id: str, image_path: Optional[str] = None) -> dict[str, Any]:
    """Synchronous twin of :func:`process_floor_plan` (still a stub)."""

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
    "process_cad_file",
    "process_floor_plan",
    "run_cad_inprocess",
    "run_cad_stub",
    "run_floor_plan_stub",
]
