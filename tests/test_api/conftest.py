"""Shared fixtures for API-level tests.

Channel B moved to the real DXF / IFC parsers in Step 6, so CAD-upload
tests can no longer rely on ``b"fake-cad-bytes"`` and have to post an
actually-parseable payload.  The helpers here build tiny in-memory
fixtures that exercise the full parser → builder → scorer path without
bloating the test suite with on-disk sample files.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def sample_dxf_bytes() -> bytes:
    """Build a 20×15 m DXF plan with walls, grid, a room, and one door."""

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

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sample.dxf"
        doc.saveas(str(p))
        return p.read_bytes()


@pytest.fixture()
def sample_ifc_bytes() -> bytes:
    """Build a minimal IFC4 file with one storey and one IfcWall."""

    ifcopenshell = pytest.importorskip("ifcopenshell")
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Sample")
    ifcopenshell.api.run(
        "unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETERS"}
    )
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
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
        "aggregate.assign_object", model, relating_object=building, products=[storey]
    )

    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="W1")
    ifcopenshell.api.run(
        "spatial.assign_container",
        model,
        relating_structure=storey,
        products=[wall],
    )

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sample.ifc"
        model.write(str(p))
        return p.read_bytes()


@pytest.fixture()
def sample_png_bytes() -> bytes:
    """Tiny 16×16 white PNG — still accepted by the image upload endpoint."""

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()
