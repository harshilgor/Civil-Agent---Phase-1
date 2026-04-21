"""Step-6 Channel B: real DXF / IFC parsing through ``process_cad_file``.

These tests drive ``_run_cad_pipeline`` and the Celery task dispatch
path end-to-end against on-disk fixtures.  They are the guardrail that
any future refactor of the parser or graph-builder layer still stamps
the right provenance / assumptions / completeness scores on the
emitted ``BuildingGraph``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

celery = pytest.importorskip("celery")

from src.schema.building_graph import BuildingGraph
from src.schema.enums import DetectorSource, InputSource


# ---------------------------------------------------------------------------
# Fixture builders (local so the tests remain hermetic).
# ---------------------------------------------------------------------------


@pytest.fixture()
def dxf_plan_path(tmp_path) -> Path:
    """20 × 15 m plan with walls, grid, a room label, and one door."""

    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    doc.layers.add("A-WALL")
    for s, e in [
        ((0, 0), (20000, 0)),
        ((20000, 0), (20000, 15000)),
        ((20000, 15000), (0, 15000)),
        ((0, 15000), (0, 0)),
        ((10000, 0), (10000, 15000)),
    ]:
        msp.add_line(s, e, dxfattribs={"layer": "A-WALL"})

    doc.layers.add("S-GRID")
    for x in [0, 10000, 20000]:
        msp.add_line((x, -1000), (x, 16000), dxfattribs={"layer": "S-GRID"})
    for y in [0, 7500, 15000]:
        msp.add_line((-1000, y), (21000, y), dxfattribs={"layer": "S-GRID"})

    doc.layers.add("A-ROOM")
    msp.add_lwpolyline(
        [(0, 0), (10000, 0), (10000, 15000), (0, 15000)],
        dxfattribs={"layer": "A-ROOM"},
        close=True,
    )
    msp.add_text(
        "OFFICE",
        dxfattribs={"layer": "A-ROOM", "insert": (5000, 7500), "height": 400},
    )

    doc.layers.add("A-DOOR")
    msp.add_line((4500, 0), (5500, 0), dxfattribs={"layer": "A-DOOR"})

    out = tmp_path / "plan.dxf"
    doc.saveas(str(out))
    return out


@pytest.fixture()
def ifc_plan_path(tmp_path) -> Path:
    ifcopenshell = pytest.importorskip("ifcopenshell")
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcProject", name="Sample"
    )
    ifcopenshell.api.run(
        "unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETERS"}
    )
    site = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcSite", name="Site"
    )
    building = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuilding", name="Building"
    )
    storey = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1"
    )
    storey.Elevation = 0.0

    project = model.by_type("IfcProject")[0]
    ifcopenshell.api.run(
        "aggregate.assign_object", model, relating_object=project, products=[site]
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", model, relating_object=site, products=[building]
    )
    ifcopenshell.api.run(
        "aggregate.assign_object",
        model,
        relating_object=building,
        products=[storey],
    )

    wall = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcWall", name="W1"
    )
    ifcopenshell.api.run(
        "spatial.assign_container",
        model,
        relating_structure=storey,
        products=[wall],
    )

    out = tmp_path / "plan.ifc"
    model.write(str(out))
    return out


def _to_graph(payload: dict) -> BuildingGraph:
    assert "building_graph" in payload
    return BuildingGraph.model_validate(payload["building_graph"])


# ---------------------------------------------------------------------------
# DXF end-to-end
# ---------------------------------------------------------------------------


class TestDxfPipeline:
    def test_run_cad_pipeline_dxf_produces_graph(self, dxf_plan_path: Path) -> None:
        from src.worker.tasks import _run_cad_pipeline

        payload = _run_cad_pipeline("job-dxf-1", str(dxf_plan_path), "DXF")
        assert payload["status"] == "ok"
        assert payload["file_type"] == "DXF"
        graph = _to_graph(payload)
        assert graph.metadata.input_source == InputSource.DXF_FILE
        assert graph.metadata.job_id == "job-dxf-1"
        # Fixture has 5 wall lines (outer rect + 1 interior).
        assert len(graph.walls) >= 4

    def test_dxf_walls_stamped_with_cad_direct_provenance(
        self, dxf_plan_path: Path
    ) -> None:
        from src.worker.tasks import _run_cad_pipeline

        graph = _to_graph(
            _run_cad_pipeline("job-dxf-2", str(dxf_plan_path), "DXF")
        )
        for wall in graph.walls:
            assert wall.provenance is not None
            assert wall.provenance.detector_source == DetectorSource.CAD_DIRECT
            # CAD geometry is user-authoritative → confidence is 1.0,
            # not the 0.0-signalling-stub contract of Step 5.
            assert wall.provenance.confidence_from_model == 1.0

    def test_dxf_pipeline_records_assumptions(self, dxf_plan_path: Path) -> None:
        from src.worker.tasks import _run_cad_pipeline

        graph = _to_graph(
            _run_cad_pipeline("job-dxf-3", str(dxf_plan_path), "DXF")
        )
        register = graph.metadata.assumption_register
        assert register, "CadAssumptionBuilder must populate the register"
        # Input channel is always logged as immutable.
        sources = {a.id for a in register}
        assert any("input_source" in sid or "channel" in sid for sid in sources), (
            f"expected an input-source assumption, got {sources}"
        )

    def test_dxf_pipeline_is_user_authoritative_for_completeness(
        self, dxf_plan_path: Path
    ) -> None:
        from src.worker.tasks import _run_cad_pipeline

        graph = _to_graph(
            _run_cad_pipeline("job-dxf-4", str(dxf_plan_path), "DXF")
        )
        # CAD inputs aren't penalised for missing YOLO / symbol detectors.
        assert graph.metadata.completeness.missing_subsystems == []


# ---------------------------------------------------------------------------
# IFC end-to-end
# ---------------------------------------------------------------------------


class TestIfcPipeline:
    def test_run_cad_pipeline_ifc_produces_graph(self, ifc_plan_path: Path) -> None:
        from src.worker.tasks import _run_cad_pipeline

        payload = _run_cad_pipeline("job-ifc-1", str(ifc_plan_path), "IFC")
        assert payload["file_type"] == "IFC"
        graph = _to_graph(payload)
        assert graph.metadata.input_source == InputSource.IFC_FILE

    def test_ifc_walls_stamped_with_ifc_direct_provenance(
        self, ifc_plan_path: Path
    ) -> None:
        from src.worker.tasks import _run_cad_pipeline

        graph = _to_graph(
            _run_cad_pipeline("job-ifc-2", str(ifc_plan_path), "IFC")
        )
        for wall in graph.walls:
            assert wall.provenance is not None
            assert wall.provenance.detector_source == DetectorSource.IFC_DIRECT
            assert wall.provenance.confidence_from_model == 1.0


# ---------------------------------------------------------------------------
# DWG failure surfaces cleanly
# ---------------------------------------------------------------------------


class TestDwgFailure:
    def test_dwg_without_converter_raises_dwg_unsupported(
        self, tmp_path
    ) -> None:
        from src.worker.tasks import DWGUnsupportedError, _run_cad_pipeline

        dwg_path = tmp_path / "plan.dwg"
        dwg_path.write_bytes(b"fake-dwg-bytes")

        with pytest.raises(DWGUnsupportedError):
            _run_cad_pipeline("job-dwg-1", str(dwg_path), "DWG")

    def test_dwg_task_under_eager_marks_failure(self, tmp_path) -> None:
        """The Celery task must propagate DWG failure rather than returning
        stub data; eager mode surfaces this as a failed AsyncResult."""

        from src.worker.tasks import process_cad_file

        dwg_path = tmp_path / "plan.dwg"
        dwg_path.write_bytes(b"fake-dwg-bytes")

        assert process_cad_file is not None
        with pytest.raises(Exception):
            process_cad_file.delay("job-dwg-2", str(dwg_path), "DWG").get()


class TestDwgIntermediateCleanup:
    """The ODA converter writes a sibling .dxf next to the source.  That
    intermediate has to be removed after parsing or a worker processing
    many files will silently fill the staging volume.
    """

    def test_intermediate_dxf_removed_on_success(
        self, tmp_path, monkeypatch
    ) -> None:
        """Stub out ``DWGConverter.convert`` so the test doesn't require
        the proprietary ODA binary.  Simulate a successful conversion by
        writing a valid DXF next to the source, then confirm
        ``_parse_dwg`` deletes it once parsing completes."""

        import ezdxf

        from src.parsers import dwg_converter
        from src.worker import tasks as worker_tasks

        dwg_path = tmp_path / "plan.dwg"
        dwg_path.write_bytes(b"fake-dwg-bytes")
        sibling_dxf = dwg_path.with_suffix(".dxf")

        def fake_convert(self, src):  # noqa: ARG001
            doc = ezdxf.new("R2010")
            msp = doc.modelspace()
            doc.layers.add("A-WALL")
            msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL"})
            doc.saveas(str(sibling_dxf))
            return sibling_dxf

        monkeypatch.setattr(dwg_converter.DWGConverter, "convert", fake_convert)

        parsed = worker_tasks._parse_dwg(dwg_path)
        assert "walls" in parsed
        assert not sibling_dxf.exists(), (
            "intermediate DXF must be removed after a successful parse"
        )

    def test_intermediate_dxf_removed_on_parse_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        """If DXFParser raises, the cleanup still has to run."""

        from src.parsers import dwg_converter
        from src.worker import tasks as worker_tasks

        dwg_path = tmp_path / "plan.dwg"
        dwg_path.write_bytes(b"fake-dwg-bytes")
        sibling_dxf = dwg_path.with_suffix(".dxf")

        def fake_convert(self, src):  # noqa: ARG001
            # Produce bytes that ezdxf won't accept so DXFParser raises.
            sibling_dxf.write_bytes(b"not-a-dxf")
            return sibling_dxf

        monkeypatch.setattr(dwg_converter.DWGConverter, "convert", fake_convert)

        with pytest.raises(Exception):
            worker_tasks._parse_dwg(dwg_path)
        assert not sibling_dxf.exists(), (
            "intermediate DXF must be removed even when parsing fails"
        )


# ---------------------------------------------------------------------------
# Bad input propagates as task failure (not a silent stub)
# ---------------------------------------------------------------------------


class TestBadInputPropagates:
    def test_malformed_dxf_surfaces_as_exception(self, tmp_path) -> None:
        from src.worker.tasks import _run_cad_pipeline

        bad = tmp_path / "bad.dxf"
        bad.write_bytes(b"not-a-dxf")
        with pytest.raises(Exception):
            _run_cad_pipeline("job-bad-1", str(bad), "DXF")

    def test_unknown_file_type_rejected(self, tmp_path) -> None:
        from src.worker.tasks import _run_cad_pipeline

        p = tmp_path / "x.dxf"
        p.write_bytes(b"")
        with pytest.raises(ValueError):
            _run_cad_pipeline("job-bad-2", str(p), "STEP")
