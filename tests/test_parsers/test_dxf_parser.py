"""Tests for the DXF parser and related extractors.

Creates a synthetic DXF file in a temp directory for testing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf
import pytest

from src.parsers.dxf_parser import DXFParser
from src.parsers.wall_extractor import WallExtractor
from src.parsers.grid_extractor import GridExtractor
from src.parsers.room_extractor import RoomExtractor
from src.core.graph_builder import GraphBuilder


def _create_test_dxf(path: Path) -> None:
    """Create a minimal DXF with walls, grid, rooms, and text."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Wall layer — 4 perimeter walls (in mm)
    doc.layers.add("A-WALL-FULL")
    msp.add_line((0, 0), (32000, 0), dxfattribs={"layer": "A-WALL-FULL"})
    msp.add_line((32000, 0), (32000, 24000), dxfattribs={"layer": "A-WALL-FULL"})
    msp.add_line((32000, 24000), (0, 24000), dxfattribs={"layer": "A-WALL-FULL"})
    msp.add_line((0, 24000), (0, 0), dxfattribs={"layer": "A-WALL-FULL"})

    # Interior wall
    msp.add_line((16000, 0), (16000, 24000), dxfattribs={"layer": "A-WALL-FULL"})

    # Grid layer — X direction (vertical lines)
    doc.layers.add("S-GRID")
    for x in [0, 8000, 16000, 24000, 32000]:
        msp.add_line((x, -2000), (x, 26000), dxfattribs={"layer": "S-GRID"})
    # Y direction (horizontal lines)
    for y in [0, 8000, 16000, 24000]:
        msp.add_line((-2000, y), (34000, y), dxfattribs={"layer": "S-GRID"})

    # Room layer — two closed polylines
    doc.layers.add("A-ROOM")
    msp.add_lwpolyline(
        [(0, 0), (16000, 0), (16000, 24000), (0, 24000)],
        dxfattribs={"layer": "A-ROOM"},
        close=True,
    )
    msp.add_lwpolyline(
        [(16000, 0), (32000, 0), (32000, 24000), (16000, 24000)],
        dxfattribs={"layer": "A-ROOM"},
        close=True,
    )

    # Text labels — inside rooms
    msp.add_text(
        "OFFICE A",
        dxfattribs={"layer": "A-ROOM", "insert": (8000, 12000), "height": 500},
    )
    msp.add_text(
        "OFFICE B",
        dxfattribs={"layer": "A-ROOM", "insert": (24000, 12000), "height": 500},
    )

    # Grid labels
    msp.add_text("A", dxfattribs={"layer": "S-GRID", "insert": (0, -3000), "height": 400})
    msp.add_text("B", dxfattribs={"layer": "S-GRID", "insert": (8000, -3000), "height": 400})

    # Door on door layer
    doc.layers.add("A-DOOR")
    msp.add_line((8000, 0), (9000, 0), dxfattribs={"layer": "A-DOOR"})

    doc.saveas(str(path))


@pytest.fixture()
def test_dxf(tmp_path: Path) -> Path:
    p = tmp_path / "test_plan.dxf"
    _create_test_dxf(p)
    return p


class TestDXFParser:
    def test_parse_returns_all_keys(self, test_dxf: Path):
        parser = DXFParser()
        result = parser.parse(test_dxf)
        assert "walls" in result
        assert "grid_lines" in result
        assert "rooms" in result
        assert "text_annotations" in result
        assert "units" in result

    def test_walls_detected(self, test_dxf: Path):
        result = DXFParser().parse(test_dxf)
        assert len(result["walls"]) >= 5  # 4 perimeter + 1 interior

    def test_grid_lines_detected(self, test_dxf: Path):
        result = DXFParser().parse(test_dxf)
        x_count = len(result["grid_lines"]["x_lines"])
        y_count = len(result["grid_lines"]["y_lines"])
        assert x_count >= 4  # vertical lines → x positions
        assert y_count >= 3

    def test_rooms_detected(self, test_dxf: Path):
        result = DXFParser().parse(test_dxf)
        assert len(result["rooms"]) == 2

    def test_text_annotations_detected(self, test_dxf: Path):
        result = DXFParser().parse(test_dxf)
        texts = [t["text"] for t in result["text_annotations"]]
        assert "OFFICE A" in texts

    def test_doors_detected(self, test_dxf: Path):
        result = DXFParser().parse(test_dxf)
        assert len(result["doors"]) >= 1

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            DXFParser().parse("/nonexistent/file.dxf")


class TestWallExtractor:
    def test_merge_removes_short_segments(self):
        ext = WallExtractor(min_wall_length_mm=500)
        raw = [
            {"start": [0, 0], "end": [100, 0], "thickness_mm": 200},  # too short
            {"start": [0, 0], "end": [8000, 0], "thickness_mm": 200},
        ]
        result = ext.extract(raw)
        assert len(result) == 1

    def test_merge_collinear(self):
        ext = WallExtractor()
        raw = [
            {"start": [0, 0], "end": [4000, 0], "thickness_mm": 200},
            {"start": [4000, 0], "end": [8000, 0], "thickness_mm": 200},
        ]
        result = ext.extract(raw)
        assert len(result) == 1
        merged = result[0]
        assert merged["start"][0] == 0
        assert merged["end"][0] == 8000


class TestRoomExtractor:
    def test_label_classification(self):
        ext = RoomExtractor()
        rooms = ext.extract(
            [
                {
                    "polygon": [[0, 0], [8000, 0], [8000, 8000], [0, 8000], [0, 0]],
                    "label": "KITCHEN",
                },
            ],
            [],
        )
        assert len(rooms) == 1
        assert rooms[0]["type"] == "KITCHEN"

    def test_unknown_label_is_undefined(self):
        ext = RoomExtractor()
        rooms = ext.extract(
            [{"polygon": [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], "label": "XYZ"}],
            [],
        )
        assert rooms[0]["type"] == "UNDEFINED"


class TestCADToGraphBuilder:
    def test_from_cad_data_produces_valid_graph(self, test_dxf: Path):
        parsed = DXFParser().parse(test_dxf)
        builder = GraphBuilder()
        bg = builder.from_cad_data(parsed, project_name="DXF Test")
        assert bg.project.name == "DXF Test"
        assert len(bg.walls) >= 1
        assert len(bg.grid.x_lines) >= 2
        assert len(bg.stories) == 1
        assert bg.metadata.input_source.value == "DXF_FILE"

    def test_from_cad_data_serializes(self, test_dxf: Path):
        from src.schema.building_graph import BuildingGraph

        parsed = DXFParser().parse(test_dxf)
        bg = GraphBuilder().from_cad_data(parsed)
        json_str = bg.model_dump_json()
        restored = BuildingGraph.model_validate_json(json_str)
        assert restored.project.num_stories == bg.project.num_stories
