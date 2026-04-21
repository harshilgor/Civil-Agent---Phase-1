"""End-to-end integration tests for :class:`GeometryPostProcessor`.

Exercise the full six-pass pipeline against synthetic hand-built wall
graphs that trigger each pass in combination.
"""

from __future__ import annotations

import pytest

from src.core.geometry import (
    GeometryInputs,
    GeometryOutputs,
    GeometryPostProcessConfig,
    GeometryPostProcessor,
)
from src.core.geometry.rooms import RoomHint
from src.schema.building_graph import (
    Bay,
    ColumnCandidate,
    Core,
    GridLine,
    GridSystem,
    Room,
)
from src.schema.enums import CoreType, RoomType

from .conftest import wall


def _single_room_walls() -> list:
    """A 5m × 5m room, slightly rotated, walls 20mm short of the corner.

    Exactly the geometry a CV vectoriser produces — the snap + corners
    passes must clean it up before any higher-level pass can see it.
    """

    return [
        wall("w_n", (10.0, 4997.0), (4990.0, 5003.0)),
        wall("w_e", (4985.0, 4980.0), (5015.0, 20.0)),
        wall("w_s", (4990.0, 3.0), (10.0, -3.0)),
        wall("w_w", (15.0, 20.0), (-15.0, 4980.0)),
    ]


class TestMinimalRun:
    def test_dirty_single_room_becomes_clean_room(self):
        pp = GeometryPostProcessor()
        out = pp.run(GeometryInputs(walls=_single_room_walls()))

        assert isinstance(out, GeometryOutputs)
        # Snap+corners cleaned the walls — every wall axis-aligned.
        for w in out.walls:
            x_same = abs(w.start[0] - w.end[0]) < 1.0
            y_same = abs(w.start[1] - w.end[1]) < 1.0
            assert x_same or y_same

        # A single room extracted.
        assert len(out.rooms) == 1
        assert out.rooms[0].area_m2 == pytest.approx(25.0, abs=0.5)

        # No grid (four walls ≠ enough support) — still a valid output.
        assert out.grid.x_lines == []
        assert out.grid.y_lines == []
        assert out.columns == []
        assert out.cores == []

        # Assumption register: room inference + gridless note.
        assumption_ids = {a.id for a in out.assumptions}
        assert "geometry.rooms_inferred" in assumption_ids
        assert "geometry.grid_absent" in assumption_ids


class TestCadAuthoritativeInputs:
    def test_cad_grid_is_preserved_verbatim(self):
        # Pre-existing grid matching a 2-bay CAD-sourced plan.
        grid = GridSystem(
            x_lines=[
                GridLine(id="A", position_mm=0.0),
                GridLine(id="B", position_mm=7000.0),
                GridLine(id="C", position_mm=14000.0),
            ],
            y_lines=[
                GridLine(id="1", position_mm=0.0),
                GridLine(id="2", position_mm=6000.0),
            ],
            bays=[
                Bay(
                    id="A1",
                    span_x_mm=7000.0,
                    span_y_mm=6000.0,
                    grid_x_start="A",
                    grid_x_end="B",
                    grid_y_start="1",
                    grid_y_end="2",
                ),
                Bay(
                    id="B1",
                    span_x_mm=7000.0,
                    span_y_mm=6000.0,
                    grid_x_start="B",
                    grid_x_end="C",
                    grid_y_start="1",
                    grid_y_end="2",
                ),
            ],
        )

        pp = GeometryPostProcessor()
        out = pp.run(
            GeometryInputs(
                walls=_single_room_walls(),
                grid=grid,
            )
        )
        # No "grid inferred" assumption because Channel B supplied it.
        ids = {a.id for a in out.assumptions}
        assert "geometry.grid_inferred" not in ids
        assert "geometry.grid_absent" not in ids
        # Passed through verbatim.
        assert [g.id for g in out.grid.x_lines] == ["A", "B", "C"]
        assert len(out.grid.bays) == 2

    def test_cad_columns_flow_as_signal_not_passthrough(self):
        """When CAD columns are provided they feed the column scorer so
        it can combine them with wall-endpoint evidence.  The output
        ``columns`` list comes from the scorer, not raw pass-through."""

        # Build a real 2x2 grid from walls so the scorer has somewhere
        # to place candidates.
        grid_walls = []
        wid = 0
        for x in (0.0, 5000.0):
            for i in range(3):
                grid_walls.append(
                    wall(
                        f"v_{wid}",
                        (x, i * 3000.0),
                        (x, (i + 1) * 3000.0),
                    )
                )
                wid += 1
        for y in (0.0, 3000.0):
            for i in range(3):
                grid_walls.append(
                    wall(
                        f"h_{wid}",
                        (i * 3000.0, y),
                        ((i + 1) * 3000.0, y),
                    )
                )
                wid += 1

        cad_columns = [
            ColumnCandidate(
                position=[0.0, 0.0], is_required=False, confidence=1.0
            )
        ]
        pp = GeometryPostProcessor()
        out = pp.run(
            GeometryInputs(walls=grid_walls, cad_columns=cad_columns)
        )

        # Inferred columns assumption only fires when cad_columns is
        # None; here it is not None → absent.
        ids = {a.id for a in out.assumptions}
        assert "geometry.columns_inferred" not in ids
        # But columns were still emitted via the scorer, and the CAD
        # match promoted A1 to is_required.
        a1 = next(
            (c for c in out.columns if c.grid_intersection == "A1"), None
        )
        assert a1 is not None
        assert a1.is_required is True

    def test_cad_cores_preserved(self):
        preset_core = Core(
            id="cad_core",
            type=CoreType.STAIR_ONLY,
            polygon=[[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
            contains_stairs=True,
            stories=["S1"],
            confidence=1.0,
        )
        pp = GeometryPostProcessor()
        out = pp.run(
            GeometryInputs(walls=_single_room_walls(), cad_cores=[preset_core])
        )
        assert out.cores == [preset_core]
        ids = {a.id for a in out.assumptions}
        assert "geometry.cores_inferred" not in ids


class TestFullBuilding:
    def test_three_bay_with_stair_core_yields_everything(self):
        # 15m × 5m rectangle divided into 3 bays, with a 3m × 3m stair
        # room in the middle bay.  Walls are *split* at each interior
        # intersection — exactly what a real vectoriser produces and
        # what the grid-inference minimum_support_walls threshold
        # (three-wall minimum per rail) expects to see.
        walls = [
            # Outer shell: north wall split at the two dividers.
            wall("n1", (0.0, 5000.0), (5000.0, 5000.0)),
            wall("n2", (5000.0, 5000.0), (10000.0, 5000.0)),
            wall("n3", (10000.0, 5000.0), (15000.0, 5000.0)),
            # East wall split at stair-room-height boundaries.
            wall("e1", (15000.0, 5000.0), (15000.0, 4000.0)),
            wall("e2", (15000.0, 4000.0), (15000.0, 1000.0)),
            wall("e3", (15000.0, 1000.0), (15000.0, 0.0)),
            # South wall split at the two dividers.
            wall("s1", (15000.0, 0.0), (10000.0, 0.0)),
            wall("s2", (10000.0, 0.0), (5000.0, 0.0)),
            wall("s3", (5000.0, 0.0), (0.0, 0.0)),
            # West wall split at stair-room-height boundaries.
            wall("w1", (0.0, 0.0), (0.0, 1000.0)),
            wall("w2", (0.0, 1000.0), (0.0, 4000.0)),
            wall("w3", (0.0, 4000.0), (0.0, 5000.0)),
            # Interior dividers split at stair-room-height boundaries.
            wall("d1a", (5000.0, 0.0), (5000.0, 1000.0)),
            wall("d1b", (5000.0, 1000.0), (5000.0, 4000.0)),
            wall("d1c", (5000.0, 4000.0), (5000.0, 5000.0)),
            wall("d2a", (10000.0, 0.0), (10000.0, 1000.0)),
            wall("d2b", (10000.0, 1000.0), (10000.0, 4000.0)),
            wall("d2c", (10000.0, 4000.0), (10000.0, 5000.0)),
            # Stair walls — a small room in the middle bay.
            wall("st_n", (6000.0, 4000.0), (9000.0, 4000.0)),
            wall("st_s", (6000.0, 1000.0), (9000.0, 1000.0)),
            wall("st_e", (9000.0, 1000.0), (9000.0, 4000.0)),
            wall("st_w", (6000.0, 1000.0), (6000.0, 4000.0)),
        ]

        hints = [
            RoomHint(
                polygon=[
                    [6100, 1100],
                    [8900, 1100],
                    [8900, 3900],
                    [6100, 3900],
                ],
                room_type=RoomType.STAIRWELL,
                label="Stair 1",
            )
        ]

        pp = GeometryPostProcessor()
        out = pp.run(GeometryInputs(walls=walls, room_hints=hints))

        # Rooms: bay 1, bay 3, the stair room, and the annular space
        # around the stair in bay 2.  Exact count depends on
        # polygonisation; assert lower bound.
        assert len(out.rooms) >= 3

        # One of them is the stair (inherits hint).
        stair = next(
            (r for r in out.rooms if r.type == RoomType.STAIRWELL), None
        )
        assert stair is not None
        assert stair.label == "Stair 1"

        # Core detected from the stair room.
        assert len(out.cores) == 1
        assert out.cores[0].type == CoreType.STAIR_ONLY
        assert out.cores[0].contains_stairs is True

        # Grid inferred — interior dividers provide the support.
        assert len(out.grid.x_lines) >= 2  # d1 + d2 at least

        # Columns scored.
        assert len(out.columns) >= 1


class TestStatelessness:
    def test_running_twice_produces_identical_output(self):
        pp = GeometryPostProcessor()
        a = pp.run(GeometryInputs(walls=_single_room_walls()))
        b = pp.run(GeometryInputs(walls=_single_room_walls()))
        assert [w.start for w in a.walls] == [w.start for w in b.walls]
        assert [w.end for w in a.walls] == [w.end for w in b.walls]
        # Room IDs contain uuids so we compare *geometry* only.
        assert [r.polygon for r in a.rooms] == [r.polygon for r in b.rooms]

    def test_input_list_not_mutated(self):
        walls_in = _single_room_walls()
        snapshot = [(w.start.copy(), w.end.copy()) for w in walls_in]
        GeometryPostProcessor().run(GeometryInputs(walls=walls_in))
        for w, (s, e) in zip(walls_in, snapshot):
            assert w.start == s
            assert w.end == e
