"""Phase 1 Step 9 — Geometry post-processor package.

Takes already-vectorised wall segments (from either Channel B CAD or
Channel C ML output) and emits the cleaned, structural primitives
that downstream stages consume: orthogonalised walls, extracted
rooms, inferred grid, scored column candidates, and detected cores.

Public API is intentionally small: callers either instantiate a
:class:`GeometryPostProcessor` directly, or call one of the pass-level
functions (``snap_orthogonal``, ``resolve_corners``, etc.) in
isolation for testing.
"""

from __future__ import annotations

from .columns import score_columns
from .config import GeometryPostProcessConfig
from .cores import detect_cores
from .corners import resolve_corners
from .grid import infer_grid
from .post_processor import (
    GeometryInputs,
    GeometryOutputs,
    GeometryPostProcessor,
)
from .rooms import RoomHint, extract_rooms
from .snap import snap_orthogonal

__all__ = [
    "GeometryInputs",
    "GeometryOutputs",
    "GeometryPostProcessConfig",
    "GeometryPostProcessor",
    "RoomHint",
    "detect_cores",
    "extract_rooms",
    "infer_grid",
    "resolve_corners",
    "score_columns",
    "snap_orthogonal",
]
