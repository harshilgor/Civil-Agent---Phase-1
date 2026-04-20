"""Celery tasks — Step 5 stubs.

These are intentionally *synthetic* placeholders for Channels B and C.
The real CV / CAD pipelines land in later steps; for now the job is to
exercise the async plumbing end to end:

* the API endpoint submits a task via :meth:`.delay`,
* :mod:`src.api.async_job_store` registers a ``queued`` record,
* the worker (or the eager in-process runner, during tests) picks it up,
* it returns a **fixed synthetic Building Graph** that still validates
  against the Phase-1 schema,
* the polling endpoint rehydrates that graph and serves it to the
  frontend.

The synthetic graph is built by driving :class:`GraphBuilder` with a
canned :class:`StructuredInputRequest` and then relabeling the
``input_source`` / provenance so the frontend can distinguish stub data
from a real detector run.  The completeness scorer correctly penalises
the ``detector_coverage`` axis on Channel C stub output because the
image pipeline was supposed to invoke YOLO / SYMBOL_DETECTOR and didn't
— that penalty disappears automatically once the real detectors ship.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

from src.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Synthetic Building Graph factory
# ---------------------------------------------------------------------------


def _canonical_request():
    """The fixed request that drives every Step-5 stub.

    Kept deliberately minimal: six-by-five grid, three stories, office
    occupancy.  Callers then patch the input_source to match their
    channel and rewrite the per-element provenance.
    """

    # Deferred import so this module loads without FastAPI installed
    # (matters for the worker image).
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


def _build_synthetic_graph(
    job_id: str, *, input_source, source_detector
):
    """Build, relabel, and score a synthetic :class:`BuildingGraph`.

    Every wall / room / column / core in the returned graph carries
    ``provenance.detector_source == source_detector`` with
    ``confidence_from_model=0.0`` — reviewers get a very loud signal
    that these elements are placeholders, not real detections.
    """

    from src.core.graph_builder import GraphBuilder
    from src.utils.completeness_scorer import annotate_with_completeness

    builder = GraphBuilder()
    graph = builder.from_structured_input(
        _canonical_request(), run_id=job_id, job_id=job_id
    )
    graph.metadata.input_source = input_source

    # Repaint every element's provenance so the frontend / reviewer can
    # tell stub output apart from a real Channel-A submission.
    for collection in (graph.walls, graph.rooms, graph.column_candidates, graph.cores):
        for element in collection:
            prov = getattr(element, "provenance", None)
            if prov is None:
                continue
            prov.detector_source = source_detector
            prov.confidence_from_model = 0.0

    # Completeness needs to be recomputed because we flipped input_source
    # (Channel B/C rules differ from Channel A).
    return annotate_with_completeness(graph)


def _dump_graph(graph) -> dict[str, Any]:
    """Serialise a BuildingGraph to a JSON-safe dict for Celery results."""

    return graph.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tasks (only registered when Celery is importable)
# ---------------------------------------------------------------------------


if celery_app is not None:

    @celery_app.task(bind=True, name="civil_agent.process_floor_plan")
    def process_floor_plan(
        self, job_id: str, image_path: str
    ) -> dict[str, Any]:
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
        """Stub Channel-B task: pretend to parse a DXF/DWG/IFC file."""

        from src.schema.enums import DetectorSource, InputSource

        source_map = {
            "DXF": InputSource.DXF_FILE,
            "DWG": InputSource.DWG_FILE,
            "IFC": InputSource.IFC_FILE,
        }
        detector_map = {
            "DXF": DetectorSource.CAD_DIRECT,
            "DWG": DetectorSource.CAD_DIRECT,
            "IFC": DetectorSource.IFC_DIRECT,
        }
        key = file_type.upper()
        input_source = source_map.get(key, InputSource.DXF_FILE)
        source_detector = detector_map.get(key, DetectorSource.CAD_DIRECT)

        logger.info(
            "stub_process_cad_file_start",
            task_id=self.request.id,
            job_id=job_id,
            file_path=file_path,
            file_type=file_type,
        )
        t0 = time.perf_counter()
        try:
            graph = _build_synthetic_graph(
                job_id,
                input_source=input_source,
                source_detector=source_detector,
            )
            payload = _dump_graph(graph)
            logger.info(
                "stub_process_cad_file_complete",
                task_id=self.request.id,
                job_id=job_id,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            return {
                "status": "ok",
                "job_id": job_id,
                "channel": "cad",
                "file_type": key,
                "stub": True,
                "building_graph": payload,
            }
        except Exception as exc:
            logger.error(
                "stub_process_cad_file_failed",
                task_id=self.request.id,
                job_id=job_id,
                error=str(exc),
            )
            raise

else:  # pragma: no cover — Celery not installed
    process_floor_plan = None  # type: ignore[assignment]
    process_cad_file = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# In-process fallbacks (used by tests and by the graceful-degradation path
# in the endpoints when Celery isn't importable).
# ---------------------------------------------------------------------------


def run_floor_plan_stub(job_id: str, image_path: Optional[str] = None) -> dict[str, Any]:
    """Synchronous twin of :func:`process_floor_plan`."""

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


def run_cad_stub(
    job_id: str, file_path: Optional[str] = None, file_type: str = "DXF"
) -> dict[str, Any]:
    """Synchronous twin of :func:`process_cad_file`."""

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
    "_build_synthetic_graph",
    "process_cad_file",
    "process_floor_plan",
    "run_cad_stub",
    "run_floor_plan_stub",
]
