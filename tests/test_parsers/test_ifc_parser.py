"""Tests for ``src.parsers.ifc_parser``.

A minimal in-memory IFC4 model is built per-test so we exercise the
real ``ifcopenshell`` code path — no canned sample file checked in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")
import ifcopenshell.api  # noqa: E402  (imported after skip guard)

from src.core.graph_builder import GraphBuilder  # noqa: E402
from src.parsers.ifc_parser import IFCParser  # noqa: E402


def _build_minimal_ifc(path: Path, *, add_wall: bool = True) -> None:
    model = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcProject", name="Test"
    )
    ifcopenshell.api.run(
        "unit.assign_unit",
        model,
        length={"is_metric": True, "raw": "MILLIMETERS"},
    )
    site = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcSite", name="Site"
    )
    building = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuilding", name="Bld"
    )
    storey = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1"
    )
    storey.Elevation = 0.0

    project = model.by_type("IfcProject")[0]
    ifcopenshell.api.run(
        "aggregate.assign_object",
        model,
        relating_object=project,
        products=[site],
    )
    ifcopenshell.api.run(
        "aggregate.assign_object",
        model,
        relating_object=site,
        products=[building],
    )
    ifcopenshell.api.run(
        "aggregate.assign_object",
        model,
        relating_object=building,
        products=[storey],
    )

    if add_wall:
        wall = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcWall", name="W1"
        )
        ifcopenshell.api.run(
            "spatial.assign_container",
            model,
            relating_structure=storey,
            products=[wall],
        )

    model.write(str(path))


@pytest.fixture()
def ifc_file(tmp_path: Path) -> Path:
    p = tmp_path / "minimal.ifc"
    _build_minimal_ifc(p)
    return p


class TestIFCParser:
    def test_parse_returns_expected_keys(self, ifc_file: Path) -> None:
        result = IFCParser().parse(ifc_file)
        for key in (
            "walls",
            "columns",
            "rooms",
            "stories",
            "grid",
            "doors",
            "windows",
            "project_info",
            "units",
        ):
            assert key in result, f"missing {key} from IFC parser output"

    def test_parse_reports_mm_units(self, ifc_file: Path) -> None:
        result = IFCParser().parse(ifc_file)
        assert result["units"] == "mm"

    def test_parse_picks_up_one_storey(self, ifc_file: Path) -> None:
        result = IFCParser().parse(ifc_file)
        assert len(result["stories"]) == 1

    def test_parse_picks_up_wall(self, ifc_file: Path) -> None:
        result = IFCParser().parse(ifc_file)
        assert len(result["walls"]) == 1
        wall = result["walls"][0]
        assert "global_id" in wall
        assert wall["thickness_mm"] > 0

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            IFCParser().parse("/nonexistent/file.ifc")

    def test_model_without_walls_still_parses(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.ifc"
        _build_minimal_ifc(p, add_wall=False)
        result = IFCParser().parse(p)
        assert result["walls"] == []
        assert len(result["stories"]) == 1


class TestIFCToGraphBuilder:
    def test_from_cad_data_with_ifc_produces_valid_graph(
        self, ifc_file: Path
    ) -> None:
        from src.schema.enums import InputSource

        parsed = IFCParser().parse(ifc_file)
        bg = GraphBuilder().from_cad_data(
            parsed,
            project_name="IFC Test",
            input_source=InputSource.IFC_FILE,
        )
        assert bg.project.name == "IFC Test"
        assert bg.metadata.input_source == InputSource.IFC_FILE
        assert len(bg.stories) == 1
        if bg.walls:
            assert bg.walls[0].provenance.detector_source.value == "IFC_DIRECT"
