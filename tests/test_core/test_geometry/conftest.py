"""Shared fixtures for Step-9 geometry tests.

Keeps the hand-built wall graphs terse — every test builds a list of
:class:`WallSegment` from the ``wall(...)`` helper below.  Coordinates
are always in millimetres.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pytest

from src.schema.building_graph import WallSegment
from src.schema.enums import WallType


def wall(
    id_: str,
    start: Iterable[float],
    end: Iterable[float],
    *,
    thickness_mm: float = 200.0,
    type_: WallType = WallType.STRUCTURAL,
    stories: Optional[list[str]] = None,
    confidence: float = 1.0,
) -> WallSegment:
    """Terse :class:`WallSegment` constructor for synthetic graphs."""

    return WallSegment(
        id=id_,
        type=type_,
        start=[float(v) for v in start],
        end=[float(v) for v in end],
        thickness_mm=thickness_mm,
        stories=list(stories) if stories is not None else ["S1"],
        confidence=confidence,
    )


@pytest.fixture
def square_room_walls() -> list[WallSegment]:
    """A closed 5m x 5m rectangular room, four walls, exact joints."""

    return [
        wall("w_n", (0.0, 5000.0), (5000.0, 5000.0)),
        wall("w_e", (5000.0, 5000.0), (5000.0, 0.0)),
        wall("w_s", (5000.0, 0.0), (0.0, 0.0)),
        wall("w_w", (0.0, 0.0), (0.0, 5000.0)),
    ]


@pytest.fixture
def slightly_rotated_square() -> list[WallSegment]:
    """Same 5m x 5m square, but with sub-degree rotation on each wall
    and a few-millimetre endpoint misses — exactly the shape a typical
    raster vectoriser produces."""

    return [
        # Horizontal walls tilted by ~0.3°.
        wall("w_n", (0.0, 5003.0), (5000.0, 4997.0)),
        wall("w_s", (5000.0, 3.0), (0.0, -3.0)),
        # Vertical walls tilted by ~0.3°, with endpoints 20mm short.
        wall("w_e", (4997.0, 4980.0), (5003.0, 20.0)),
        wall("w_w", (3.0, 20.0), (-3.0, 4980.0)),
    ]
