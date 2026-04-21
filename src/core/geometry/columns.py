"""Step 9 — Column candidate scoring.

For every grid intersection emitted by :mod:`grid`, score it as a
column candidate on three signals:

* **Wall-endpoint proximity** — structural columns sit at wall
  joints; a wall ending at or near a grid intersection is the
  strongest vectorised signal a column is there.
* **Short wall nearby** — columns are often drawn as very short thick
  wall stubs.  A stub within the grid-proximity radius is evidence.
* **CAD column** — a column coming from Channel B is authoritative
  and promotes the candidate to ``is_required=True`` when close
  enough.

The three signals combine into a [0, 1] score via a convex mix of the
weights configured in :class:`ColumnConfig.signal_weights`.  Candidates
whose score is below :attr:`ColumnConfig.required_score` are filtered
out — they remain useful as debugging output but the public API
deliberately returns only the survivors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

import structlog

from src.schema.building_graph import (
    ColumnCandidate,
    GridSystem,
    WallSegment,
)

from .config import ColumnConfig
from .primitives import _Seg

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _IntersectionScore:
    position: list[float]
    grid_intersection: str
    endpoint_signal: float
    short_wall_signal: float
    cad_signal: float
    score: float
    cad_match: Optional[ColumnCandidate]


def score_columns(
    walls: Iterable[WallSegment],
    grid: GridSystem,
    config: ColumnConfig,
    *,
    cad_columns: Optional[list[ColumnCandidate]] = None,
    id_prefix: str = "col",
) -> list[ColumnCandidate]:
    """Public API: score grid intersections and emit column candidates.

    ``cad_columns`` (if provided) contributes the CAD signal — close
    matches are promoted to authoritative candidates with their CAD
    provenance preserved.
    """

    wall_list = list(walls)
    if not grid.x_lines or not grid.y_lines:
        return []

    segs = [_Seg.from_schema(w) for w in wall_list]
    cad_list = list(cad_columns or [])

    scored: list[_IntersectionScore] = []
    for x_line in grid.x_lines:
        for y_line in grid.y_lines:
            intersection_id = f"{x_line.id}{y_line.id}"
            pos = [x_line.position_mm, y_line.position_mm]
            scored.append(
                _score_intersection(
                    pos=pos,
                    grid_intersection=intersection_id,
                    segs=segs,
                    cad=cad_list,
                    config=config,
                )
            )

    out: list[ColumnCandidate] = []
    for i, s in enumerate(scored):
        if s.score < config.required_score:
            continue
        is_required = (
            s.cad_match is not None
            and _l2(s.position, s.cad_match.position) <= config.cad_promotion_mm
        )
        provenance = s.cad_match.provenance if s.cad_match is not None else None
        notes = _assemble_notes(s, is_required=is_required)
        out.append(
            ColumnCandidate(
                position=s.position,
                grid_intersection=s.grid_intersection,
                confidence=float(round(s.score, 4)),
                is_required=is_required,
                notes=notes,
                provenance=provenance,
            )
        )
    logger.info(
        "geometry_columns_scored",
        total_intersections=len(scored),
        emitted=len(out),
        cad_columns=len(cad_list),
    )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _score_intersection(
    *,
    pos: list[float],
    grid_intersection: str,
    segs: list[_Seg],
    cad: list[ColumnCandidate],
    config: ColumnConfig,
) -> _IntersectionScore:
    endpoint_signal = _endpoint_signal(pos, segs, radius=config.grid_proximity_mm)
    short_wall_signal = _short_wall_signal(
        pos,
        segs,
        radius=config.grid_proximity_mm,
        short_wall_max=config.short_wall_max_mm,
    )
    cad_signal, cad_match = _cad_signal(
        pos, cad, radius=config.grid_proximity_mm
    )

    weights = config.signal_weights
    raw = (
        endpoint_signal * weights.wall_endpoint
        + short_wall_signal * weights.short_wall
        + cad_signal * weights.cad_column
    )
    score = max(0.0, min(1.0, raw))
    return _IntersectionScore(
        position=pos,
        grid_intersection=grid_intersection,
        endpoint_signal=endpoint_signal,
        short_wall_signal=short_wall_signal,
        cad_signal=cad_signal,
        score=score,
        cad_match=cad_match,
    )


def _endpoint_signal(
    pos: list[float],
    segs: list[_Seg],
    *,
    radius: float,
) -> float:
    """Fraction of wall endpoints within *radius* of *pos*, scaled to
    [0, 1] where hitting 2+ endpoints saturates (any real structural
    column has at least two wall endpoints converging on it)."""

    count = 0
    for s in segs:
        if _l2(pos, s.start) <= radius:
            count += 1
        if _l2(pos, s.end) <= radius:
            count += 1
        if count >= 4:
            break
    return min(1.0, count / 2.0)


def _short_wall_signal(
    pos: list[float],
    segs: list[_Seg],
    *,
    radius: float,
    short_wall_max: float,
) -> float:
    """Binary-ish signal: 1.0 if a short wall is near *pos*, else 0.0."""

    for s in segs:
        if s.length_mm > short_wall_max:
            continue
        if (
            _l2(pos, s.start) <= radius
            or _l2(pos, s.end) <= radius
        ):
            return 1.0
    return 0.0


def _cad_signal(
    pos: list[float],
    cad: list[ColumnCandidate],
    *,
    radius: float,
) -> tuple[float, Optional[ColumnCandidate]]:
    if not cad:
        return 0.0, None
    best_match: Optional[ColumnCandidate] = None
    best_dist = float("inf")
    for c in cad:
        d = _l2(pos, c.position)
        if d <= radius and d < best_dist:
            best_dist = d
            best_match = c
    if best_match is None:
        return 0.0, None
    return 1.0, best_match


def _l2(a: list[float], b: list[float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def _assemble_notes(s: _IntersectionScore, *, is_required: bool) -> Optional[str]:
    pieces = []
    if s.cad_match is not None:
        pieces.append(
            "CAD-matched" if is_required else "CAD-adjacent"
        )
    if s.endpoint_signal > 0.0:
        pieces.append(f"endpoint={s.endpoint_signal:.2f}")
    if s.short_wall_signal > 0.0:
        pieces.append("short_wall")
    return ", ".join(pieces) if pieces else None


__all__ = ["score_columns"]
