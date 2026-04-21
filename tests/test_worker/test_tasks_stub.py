"""Step-5 worker stub tasks must return a valid synthetic BuildingGraph."""

from __future__ import annotations

import pytest

celery = pytest.importorskip("celery")

from src.schema.building_graph import BuildingGraph
from src.schema.enums import DetectorSource, InputSource


def _payload_to_graph(payload: dict) -> BuildingGraph:
    assert "building_graph" in payload
    return BuildingGraph.model_validate(payload["building_graph"])


# ---------------------------------------------------------------------------
# In-process synchronous twins (no Celery involvement).
# ---------------------------------------------------------------------------


class TestSyncTwins:
    def test_run_floor_plan_stub_returns_valid_graph(self) -> None:
        from src.worker.tasks import run_floor_plan_stub

        payload = run_floor_plan_stub("job-img-1")
        assert payload["status"] == "ok"
        assert payload["channel"] == "image"
        assert payload["stub"] is True
        assert payload["job_id"] == "job-img-1"

        graph = _payload_to_graph(payload)
        assert graph.metadata.input_source == InputSource.FLOOR_PLAN_IMAGE
        assert graph.metadata.job_id == "job-img-1"
        assert graph.walls, "stub must produce at least one wall"

    def test_floor_plan_stub_stamps_heuristic_provenance(self) -> None:
        from src.worker.tasks import run_floor_plan_stub

        graph = _payload_to_graph(run_floor_plan_stub("job-img-2"))
        for wall in graph.walls:
            assert wall.provenance is not None
            assert wall.provenance.detector_source == DetectorSource.HEURISTIC
            assert wall.provenance.confidence_from_model == 0.0

    def test_cad_stub_maps_file_type_to_input_source(self) -> None:
        from src.worker.tasks import run_cad_stub

        for ft, expected_src, expected_det in (
            ("DXF", InputSource.DXF_FILE, DetectorSource.CAD_DIRECT),
            ("DWG", InputSource.DWG_FILE, DetectorSource.CAD_DIRECT),
            ("IFC", InputSource.IFC_FILE, DetectorSource.IFC_DIRECT),
        ):
            payload = run_cad_stub("job-cad", file_type=ft)
            assert payload["file_type"] == ft
            graph = _payload_to_graph(payload)
            assert graph.metadata.input_source == expected_src
            assert all(
                w.provenance.detector_source == expected_det for w in graph.walls
            )


# ---------------------------------------------------------------------------
# Celery task invocation under task_always_eager.
# ---------------------------------------------------------------------------


class TestTaskDispatch:
    def test_floor_plan_task_delay_roundtrips(self, tmp_path) -> None:
        """``.delay()`` under eager mode drives the real Stage-1/Stage-2
        pipeline now.  The VLM classifier short-circuits to the
        "unavailable" fallback when no ``ANTHROPIC_API_KEY`` is set
        (CI default), so we don't need to mock Claude here — the
        synchronous twin keeps returning a valid BuildingGraph either
        way."""

        from PIL import Image

        from src.worker.tasks import process_floor_plan

        png_path = tmp_path / "plan.png"
        Image.new("RGB", (256, 192), color=(255, 255, 255)).save(
            str(png_path), format="PNG"
        )

        assert process_floor_plan is not None
        async_result = process_floor_plan.delay("job-delay-img", str(png_path))
        assert async_result.successful()
        payload = async_result.result
        graph = _payload_to_graph(payload)
        assert graph.metadata.input_source == InputSource.FLOOR_PLAN_IMAGE
        # Pipeline ran end-to-end (Stage 10) even without a real API
        # key or resolvable ML weights — Channel C degrades to a
        # placeholder graph rather than aborting so the user still
        # gets a reviewable BuildingGraph back.
        assert payload["stage_completed"].startswith("stage_10_")

    def test_cad_task_delay_roundtrips(self, tmp_path) -> None:
        """`.delay()` under eager mode drives the real DXF pipeline now."""

        import ezdxf

        from src.worker.tasks import process_cad_file

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        doc.layers.add("A-WALL")
        msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL"})
        msp.add_line((5000, 0), (5000, 4000), dxfattribs={"layer": "A-WALL"})
        msp.add_line((5000, 4000), (0, 4000), dxfattribs={"layer": "A-WALL"})
        msp.add_line((0, 4000), (0, 0), dxfattribs={"layer": "A-WALL"})
        dxf_path = tmp_path / "plan.dxf"
        doc.saveas(str(dxf_path))

        assert process_cad_file is not None
        async_result = process_cad_file.delay(
            "job-delay-cad", str(dxf_path), "DXF"
        )
        assert async_result.successful()
        payload = async_result.result
        assert payload["file_type"] == "DXF"
        graph = _payload_to_graph(payload)
        assert graph.metadata.input_source == InputSource.DXF_FILE
        assert len(graph.walls) >= 3


# ---------------------------------------------------------------------------
# Determinism / completeness interaction.
# ---------------------------------------------------------------------------


class TestGraphProperties:
    def test_stub_is_deterministic(self) -> None:
        """Two runs of the same stub must produce the same structural shape.

        Field-for-field equality is not a contract (UUIDs, timestamps),
        but the wall / room counts and grid dimensions must match so the
        polling UI doesn't see a different graph on reconnect.
        """

        from src.worker.tasks import run_floor_plan_stub

        g1 = _payload_to_graph(run_floor_plan_stub("job-a"))
        g2 = _payload_to_graph(run_floor_plan_stub("job-b"))

        assert len(g1.walls) == len(g2.walls)
        assert len(g1.rooms) == len(g2.rooms)
        assert len(g1.column_candidates) == len(g2.column_candidates)
        assert len(g1.stories) == len(g2.stories)

    def test_completeness_reflects_channel_c_penalty(self) -> None:
        """Channel-C stub has no real detectors; missing subsystems populate."""

        from src.worker.tasks import run_floor_plan_stub

        graph = _payload_to_graph(run_floor_plan_stub("job-c"))
        assert graph.metadata.completeness is not None
        # No openings / no YOLO columns → both detectors flagged missing.
        assert DetectorSource.SYMBOL_DETECTOR.value in graph.metadata.completeness.missing_subsystems

    def test_cad_stub_does_not_flag_ml_detectors(self) -> None:
        """Channel-B stub is user-authoritative; missing_subsystems stays []."""

        from src.worker.tasks import run_cad_stub

        graph = _payload_to_graph(run_cad_stub("job-cad-b", file_type="DXF"))
        assert graph.metadata.completeness is not None
        assert graph.metadata.completeness.missing_subsystems == []
