"""Step 9 — Grid inference.

Given a list of axis-aligned (post-snap) wall segments, extract a
:class:`GridSystem` by clustering wall positions along each axis and
keeping only clusters with enough supporting wall length.  The
resulting grid lines are deterministically labelled 'A', 'B', ... on
the X axis and '1', '2', ... on the Y axis — the convention used by
every architectural plan.

Bays are derived directly from adjacent grid-line pairs.  No
structural analysis is done here; that's later stages' concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import structlog

from src.schema.building_graph import Bay, GridLine, GridSystem, WallSegment

from .config import GridConfig
from .primitives import _Seg, cluster_1d

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GridCandidate:
    """Intermediate representation while clustering — survives the
    minimum-support filter or gets dropped."""

    position_mm: float
    supporting_wall_ids: list[str]
    total_support_length_mm: float


def infer_grid(
    walls: Iterable[WallSegment],
    config: GridConfig,
) -> GridSystem:
    """Public API: infer a :class:`GridSystem` from *walls*.

    Always returns a valid :class:`GridSystem` — possibly empty of
    lines and bays when the wall graph does not carry enough evidence.
    An empty grid is a valid output that downstream stages can key off.
    """

    wall_list = list(walls)
    if not wall_list:
        return GridSystem(x_lines=[], y_lines=[], bays=[])

    segs = [_Seg.from_schema(w) for w in wall_list]

    # Walls contributing to the X grid are vertical (share an X coord);
    # walls contributing to the Y grid are horizontal.  Near-axis walls
    # from the snap pass all land with exactly-matching coordinates
    # (modulo floating-point noise), so a coarse tolerance is fine here.
    x_candidates = _cluster_axis(
        segs, coord="x", config=config
    )
    y_candidates = _cluster_axis(
        segs, coord="y", config=config
    )

    x_lines = _to_grid_lines(x_candidates, axis="x")
    y_lines = _to_grid_lines(y_candidates, axis="y")

    bays = _build_bays(x_lines, y_lines, min_span_mm=config.min_bay_span_mm)

    logger.info(
        "geometry_grid_inferred",
        walls=len(wall_list),
        x_lines=len(x_lines),
        y_lines=len(y_lines),
        bays=len(bays),
    )
    return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays)


def _cluster_axis(
    segs: list[_Seg],
    *,
    coord: str,
    config: GridConfig,
) -> list[GridCandidate]:
    """Cluster wall positions along *coord* and filter by support."""

    idx = 0 if coord == "x" else 1
    # Pick walls whose endpoints share the coord — i.e. the wall is
    # oriented along the OTHER axis and therefore contributes to THIS
    # axis's grid.  Vertical walls (shared X) contribute to the X grid.
    contributing: list[tuple[float, float, str]] = []
    for s in segs:
        if abs(s.start[idx] - s.end[idx]) > 1e-3:
            continue  # Not axis-aligned on this coord.
        contributing.append((s.start[idx], s.length_mm, s.id))

    if not contributing:
        return []

    values = [c[0] for c in contributing]
    weights = [c[1] for c in contributing]
    clusters = cluster_1d(
        values, tolerance=config.cluster_tolerance_mm, weights=weights
    )

    candidates: list[GridCandidate] = []
    for center, members in clusters:
        supporting_ids = [contributing[m][2] for m in members]
        total_length = sum(contributing[m][1] for m in members)
        if len(members) < config.minimum_support_walls:
            continue
        if total_length < config.minimum_support_length_mm:
            continue
        candidates.append(
            GridCandidate(
                position_mm=float(center),
                supporting_wall_ids=supporting_ids,
                total_support_length_mm=float(total_length),
            )
        )
    return candidates


def _to_grid_lines(candidates: list[GridCandidate], *, axis: str) -> list[GridLine]:
    """Convert candidates to :class:`GridLine` with A/B/… or 1/2/… IDs."""

    sorted_candidates = sorted(candidates, key=lambda c: c.position_mm)
    lines: list[GridLine] = []
    for i, c in enumerate(sorted_candidates):
        lines.append(
            GridLine(id=_grid_label(axis, i), position_mm=c.position_mm)
        )
    return lines


def _grid_label(axis: str, index: int) -> str:
    """Deterministic label: 'A', 'B', ..., 'Z', 'AA', 'AB', ... on X;
    '1', '2', ... on Y."""

    if axis == "x":
        # Excel-style column labels.
        label = ""
        n = index
        while True:
            label = chr(ord("A") + n % 26) + label
            n = n // 26 - 1
            if n < 0:
                break
        return label
    return str(index + 1)


def _build_bays(
    x_lines: list[GridLine],
    y_lines: list[GridLine],
    *,
    min_span_mm: float,
) -> list[Bay]:
    bays: list[Bay] = []
    for i in range(len(x_lines) - 1):
        x_start = x_lines[i]
        x_end = x_lines[i + 1]
        span_x = x_end.position_mm - x_start.position_mm
        if span_x < min_span_mm:
            continue
        for j in range(len(y_lines) - 1):
            y_start = y_lines[j]
            y_end = y_lines[j + 1]
            span_y = y_end.position_mm - y_start.position_mm
            if span_y < min_span_mm:
                continue
            bays.append(
                Bay(
                    id=f"{x_start.id}{y_start.id}",
                    span_x_mm=float(span_x),
                    span_y_mm=float(span_y),
                    grid_x_start=x_start.id,
                    grid_x_end=x_end.id,
                    grid_y_start=y_start.id,
                    grid_y_end=y_end.id,
                )
            )
    return bays


__all__ = ["GridCandidate", "infer_grid"]
