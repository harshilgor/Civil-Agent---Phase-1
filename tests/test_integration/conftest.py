"""Fixtures for Phase 1 end-to-end integration tests.

Most byte-builder fixtures are shared with ``tests/test_api/conftest.py``
and re-exported here; the DXF fixture is bespoke because the
integration test asserts the literal-mm envelope, which requires a
DXF whose ``$INSUNITS`` header says "millimetres" rather than the
ezdxf default of "metres".
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.test_api.conftest import (  # noqa: F401
    sample_ifc_bytes,
    sample_png_bytes,
)


@pytest.fixture()
def e2e_dxf_bytes() -> bytes:
    """A 20 000 × 15 000 mm DXF with ``$INSUNITS`` explicitly set to mm.

    Why not reuse ``sample_dxf_bytes`` from the API conftest?
    ``ezdxf.new`` defaults ``$INSUNITS`` to ``6`` (metres), which the
    DXF parser faithfully converts: 20 000 metres → 20 000 000 mm.
    That's fine for tests that only assert element *presence*, but the
    Phase 1 E2E contract test asserts the literal envelope matches the
    DXF it uploaded, which requires INSUNITS=4 (mm).  Rather than
    mutate the widely-used shared fixture we keep a bespoke mm-unit
    version here.
    """

    import ezdxf

    doc = ezdxf.new("R2010")
    # INSUNITS=4 → millimetres.  The parser reads this and skips the
    # metre-to-mm conversion, so 20 000 stays 20 000.
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    doc.layers.add("A-WALL")
    for s, e in (
        ((0, 0), (20000, 0)),
        ((20000, 0), (20000, 15000)),
        ((20000, 15000), (0, 15000)),
        ((0, 15000), (0, 0)),
        ((10000, 0), (10000, 15000)),
    ):
        msp.add_line(s, e, dxfattribs={"layer": "A-WALL"})

    doc.layers.add("S-GRID")
    for x in (0, 10000, 20000):
        msp.add_line((x, -1000), (x, 16000), dxfattribs={"layer": "S-GRID"})
    for y in (0, 7500, 15000):
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
        p = Path(td) / "e2e_plan.dxf"
        doc.saveas(str(p))
        return p.read_bytes()
