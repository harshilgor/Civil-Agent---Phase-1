"""Span mapping — computes span distributions from grid bays.

Produces a ``SpanMap`` describing min / max / typical spans and a regularity
metric. Also classifies each bay (short / typical / long, square / elongated).
"""

from __future__ import annotations

import logging
import statistics

from src.schema.building_graph import BuildingGraph
from src.schema.structural_graph import SpanInfo, SpanMap
from src.structural.config import DEFAULT_CONFIG, StructuralConfig

logger = logging.getLogger(__name__)


class SpanMapper:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def map(self, graph: BuildingGraph) -> SpanMap:
        cfg = self.config.spans
        spans: list[SpanInfo] = []
        for bay in graph.grid.bays:
            sx, sy = bay.span_x_mm, bay.span_y_mm
            # Degenerate / tiny bays: max(min)/max(max) with a floor on the
            # denominator can invert "long" vs "short"; use ratio of the two
            # sides (always >= 1).
            sx = max(float(sx), 1e-6)
            sy = max(float(sy), 1e-6)
            aspect = max(sx / sy, sy / sx)

            if aspect <= cfg.square_aspect_max:
                classification = "square"
            elif aspect <= cfg.elongated_aspect_max:
                classification = "elongated"
            else:
                classification = "highly_elongated"

            spans.append(
                SpanInfo(
                    bay_id=bay.id,
                    span_x_mm=sx,
                    span_y_mm=sy,
                    aspect_ratio=aspect,
                    classification=classification,
                    support_start=f"{bay.grid_x_start}-{bay.grid_y_start}",
                    support_end=f"{bay.grid_x_end}-{bay.grid_y_end}",
                )
            )

        if not spans:
            return SpanMap()

        all_spans = [s.span_x_mm for s in spans] + [s.span_y_mm for s in spans]
        mean_span = statistics.mean(all_spans)
        max_span = max(all_spans)
        min_span = min(all_spans)
        typical = statistics.median(all_spans)
        stddev = statistics.stdev(all_spans) if len(all_spans) >= 2 else 0.0
        cv = stddev / mean_span if mean_span > 0 else 0.0
        regularity = max(0.0, 1.0 - cv)

        return SpanMap(
            spans=spans,
            max_span_mm=max_span,
            min_span_mm=min_span,
            typical_span_mm=typical,
            span_regularity=regularity,
        )
