"""Structural grid generation from building dimensions and preferences.

The grid generator divides a building footprint into a regular (or
constraint-modified) structural grid.  Grid lines are labelled A, B, C, …
in the X direction and 1, 2, 3, … in the Y direction.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass

import structlog

from src.schema.building_graph import Bay, GridLine, GridSystem

logger = structlog.get_logger(__name__)

# After Z we go AA, AB, …  — supports up to 702 grid lines per axis.
_ALPHA_LABELS = list(string.ascii_uppercase) + [
    f"{a}{b}" for a in string.ascii_uppercase for b in string.ascii_uppercase
]


@dataclass(frozen=True)
class _GridDivision:
    """Internal result of dividing one axis."""

    positions: list[float]
    bay_sizes: list[float]


class GridGenerator:
    """Generate a structural grid system from building dimensions.

    Args:
        merge_tolerance_mm: When a constraint position is within this
            distance of an existing grid line, they are merged.
    """

    def __init__(self, merge_tolerance_mm: float = 200.0) -> None:
        self._merge_tol = merge_tolerance_mm

    def generate(
        self,
        length_mm: float,
        width_mm: float,
        preferred_bay_x_mm: float = 8000,
        preferred_bay_y_mm: float = 8000,
        min_bay_mm: float = 4000,
        max_bay_mm: float = 15000,
        x_constraints: list[float] | None = None,
        y_constraints: list[float] | None = None,
    ) -> GridSystem:
        """Build a ``GridSystem`` for the given footprint.

        Algorithm
        ---------
        1. Divide each axis by the preferred bay size → number of bays.
        2. Clamp bay size to [min_bay, max_bay] adjusting bay count.
        3. Generate evenly-spaced grid lines along each axis.
        4. Merge user-specified constraint positions into the grid.
        5. Label lines (A–Z… for X, 1–N for Y) and generate Bay objects.
        """
        x_constraints = x_constraints or []
        y_constraints = y_constraints or []

        x_div = self._divide_axis(
            length_mm, preferred_bay_x_mm, min_bay_mm, max_bay_mm, x_constraints
        )
        y_div = self._divide_axis(
            width_mm, preferred_bay_y_mm, min_bay_mm, max_bay_mm, y_constraints
        )

        x_lines = [
            GridLine(id=_ALPHA_LABELS[i], position_mm=pos)
            for i, pos in enumerate(x_div.positions)
        ]
        y_lines = [
            GridLine(id=str(i + 1), position_mm=pos)
            for i, pos in enumerate(y_div.positions)
        ]

        bays = self._build_bays(x_lines, y_lines, x_div.bay_sizes, y_div.bay_sizes)

        logger.info(
            "grid_generated",
            x_bays=len(x_div.bay_sizes),
            y_bays=len(y_div.bay_sizes),
            x_range=[x_div.positions[0], x_div.positions[-1]],
            y_range=[y_div.positions[0], y_div.positions[-1]],
        )
        return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _divide_axis(
        self,
        total_mm: float,
        preferred_bay_mm: float,
        min_bay_mm: float,
        max_bay_mm: float,
        constraints: list[float],
    ) -> _GridDivision:
        """Divide *total_mm* into bays respecting size limits and constraints."""
        num_bays = max(1, round(total_mm / preferred_bay_mm))
        bay_size = total_mm / num_bays

        if bay_size < min_bay_mm and num_bays > 1:
            num_bays -= 1
            bay_size = total_mm / num_bays
        if bay_size > max_bay_mm:
            num_bays += 1
            bay_size = total_mm / num_bays

        # Clamp iteratively until stable
        for _ in range(10):
            if bay_size < min_bay_mm and num_bays > 1:
                num_bays -= 1
                bay_size = total_mm / num_bays
            elif bay_size > max_bay_mm:
                num_bays += 1
                bay_size = total_mm / num_bays
            else:
                break

        positions = [round(i * bay_size, 2) for i in range(num_bays + 1)]
        # Ensure last position is exactly total_mm
        positions[-1] = total_mm

        positions = self._merge_constraints(positions, constraints, total_mm)

        bay_sizes = [
            round(positions[i + 1] - positions[i], 2)
            for i in range(len(positions) - 1)
        ]
        return _GridDivision(positions=positions, bay_sizes=bay_sizes)

    def _merge_constraints(
        self,
        positions: list[float],
        constraints: list[float],
        total_mm: float,
    ) -> list[float]:
        """Merge constraint positions into the grid line list.

        If a constraint is within ``merge_tolerance_mm`` of an existing
        position, the existing position is moved to the constraint.
        Otherwise the constraint is inserted as a new grid line.
        """
        for c in sorted(constraints):
            if c < 0 or c > total_mm:
                logger.warning("constraint_out_of_range", constraint=c, total=total_mm)
                continue
            merged = False
            for idx, pos in enumerate(positions):
                if abs(pos - c) <= self._merge_tol:
                    positions[idx] = c
                    merged = True
                    break
            if not merged:
                positions.append(c)
        positions = sorted(set(positions))
        return positions

    @staticmethod
    def _build_bays(
        x_lines: list[GridLine],
        y_lines: list[GridLine],
        x_bays: list[float],
        y_bays: list[float],
    ) -> list[Bay]:
        bays: list[Bay] = []
        for i, sx in enumerate(x_bays):
            for j, sy in enumerate(y_bays):
                bays.append(
                    Bay(
                        id=f"bay-{x_lines[i].id}-{y_lines[j].id}",
                        span_x_mm=sx,
                        span_y_mm=sy,
                        grid_x_start=x_lines[i].id,
                        grid_x_end=x_lines[i + 1].id,
                        grid_y_start=y_lines[j].id,
                        grid_y_end=y_lines[j + 1].id,
                    )
                )
        return bays
