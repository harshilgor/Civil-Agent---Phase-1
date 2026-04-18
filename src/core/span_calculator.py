"""Span computation from a structural grid.

For every bay, computes clear spans and aggregates building-wide statistics
such as max/min span, typical span, and aspect ratios.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mode, StatisticsError

import structlog

from src.schema.building_graph import GridSystem

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BaySpanInfo:
    """Span metadata for a single bay."""

    bay_id: str
    span_x_mm: float
    span_y_mm: float
    aspect_ratio: float  # long / short


@dataclass(frozen=True)
class SpanSummary:
    """Building-wide span statistics."""

    bays: list[BaySpanInfo]
    max_span_mm: float
    min_span_mm: float
    typical_span_x_mm: float
    typical_span_y_mm: float
    max_aspect_ratio: float


class SpanCalculator:
    """Compute span metrics from a ``GridSystem``."""

    def compute_spans(self, grid: GridSystem) -> SpanSummary:
        """Analyse every bay in *grid* and return a ``SpanSummary``.

        Typical span is the statistical mode of bay sizes rounded to the
        nearest mm; if no mode exists we fall back to the mean.
        """
        if not grid.bays:
            return SpanSummary(
                bays=[],
                max_span_mm=0,
                min_span_mm=0,
                typical_span_x_mm=0,
                typical_span_y_mm=0,
                max_aspect_ratio=0,
            )

        bay_infos: list[BaySpanInfo] = []
        all_x: list[float] = []
        all_y: list[float] = []

        for bay in grid.bays:
            long = max(bay.span_x_mm, bay.span_y_mm)
            short = min(bay.span_x_mm, bay.span_y_mm)
            ratio = long / short if short > 0 else float("inf")
            bay_infos.append(
                BaySpanInfo(
                    bay_id=bay.id,
                    span_x_mm=bay.span_x_mm,
                    span_y_mm=bay.span_y_mm,
                    aspect_ratio=round(ratio, 3),
                )
            )
            all_x.append(bay.span_x_mm)
            all_y.append(bay.span_y_mm)

        all_spans = all_x + all_y

        summary = SpanSummary(
            bays=bay_infos,
            max_span_mm=max(all_spans),
            min_span_mm=min(all_spans),
            typical_span_x_mm=self._typical(all_x),
            typical_span_y_mm=self._typical(all_y),
            max_aspect_ratio=max(b.aspect_ratio for b in bay_infos),
        )
        logger.info(
            "spans_computed",
            num_bays=len(bay_infos),
            max_span=summary.max_span_mm,
            min_span=summary.min_span_mm,
        )
        return summary

    @staticmethod
    def _typical(values: list[float]) -> float:
        """Return the mode of rounded values; fall back to mean."""
        if not values:
            return 0
        rounded = [round(v) for v in values]
        try:
            return float(mode(rounded))
        except StatisticsError:
            return round(sum(values) / len(values), 2)
