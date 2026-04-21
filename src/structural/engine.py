"""Phase 2 Structural Abstraction Engine orchestrator.

Runs the seven submodules in the correct order and returns a
``StructuralDesignGraph``.

Submodule execution order:
  1. StructuralZoner
  2. SupportCandidateGenerator (also emits ForbiddenRegions)
  3. VerticalContinuityAnalyzer
  4. SpanMapper
  5. FramingDirectionInferrer
  6. GravitySystemEligibilityEvaluator
  7. LateralSystemCandidateGenerator
  8. ConstraintCompiler
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.schema.building_graph import BuildingGraph
from src.schema.structural_enums import SupportCandidateClass
from src.schema.structural_graph import StructuralDesignGraph, StructuralMetadata
from src.structural.config import DEFAULT_CONFIG, StructuralConfig
from src.structural.constraints import ConstraintCompiler
from src.structural.framing import FramingDirectionInferrer
from src.structural.gravity import GravitySystemEligibilityEvaluator
from src.structural.lateral import LateralSystemCandidateGenerator
from src.structural.spans import SpanMapper
from src.structural.supports import SupportCandidateGenerator
from src.structural.vertical import VerticalContinuityAnalyzer
from src.structural.zoner import StructuralZoner

logger = logging.getLogger(__name__)


class StructuralEngine:
    """Orchestrator for the Phase 2 Structural Abstraction Engine."""

    def __init__(self, config: Optional[StructuralConfig] = None) -> None:
        self.config = config or DEFAULT_CONFIG
        self.zoner = StructuralZoner(self.config)
        self.support_gen = SupportCandidateGenerator(self.config)
        self.vertical = VerticalContinuityAnalyzer(self.config)
        self.span_mapper = SpanMapper(self.config)
        self.framing = FramingDirectionInferrer(self.config)
        self.gravity = GravitySystemEligibilityEvaluator(self.config)
        self.lateral = LateralSystemCandidateGenerator(self.config)
        self.constraints = ConstraintCompiler(self.config)

    def build(self, graph: BuildingGraph, graph_id: str = "building-1") -> StructuralDesignGraph:
        t0 = time.perf_counter()
        warnings: list[str] = []
        assumptions: list[str] = []

        # 1. Zones
        zones = self.zoner.classify(graph)
        logger.info("structural_zoner_done", extra={"zone_count": len(zones)})

        # 2. Supports + forbidden regions
        supports, forbidden = self.support_gen.generate(graph, zones)
        logger.info(
            "support_generation_done",
            extra={
                "candidate_count": len(supports),
                "forbidden_count": len(forbidden),
            },
        )

        # 3. Vertical continuity
        supports, vertical_groups = self.vertical.analyze(supports, graph)
        logger.info("vertical_continuity_done",
                    extra={"group_count": len(vertical_groups)})

        # 4. Spans
        span_map = self.span_mapper.map(graph)
        if not span_map.spans:
            warnings.append("no_spans_from_grid")
            assumptions.append("Grid had no bays; spans inferred as empty")

        # 5. Framing
        framing_zones = self.framing.infer(graph, zones, span_map)

        # 6. Gravity
        gravity = self.gravity.evaluate(graph, span_map)

        # 7. Lateral
        lateral = self.lateral.generate(graph, zones)

        # 8. Constraints
        constraints = self.constraints.compile(
            graph=graph,
            zones=zones,
            support_candidates=supports,
            forbidden_regions=forbidden,
            vertical_groups=vertical_groups,
            span_map=span_map,
            lateral_candidates=lateral,
        )

        # Metadata
        elapsed = time.perf_counter() - t0
        confidence = self._overall_confidence(
            supports=supports,
            gravity=gravity,
            lateral=lateral,
            span_map=span_map,
        )
        regularity = self._regularity_label(span_map.span_regularity)

        metadata = StructuralMetadata(
            processing_time_seconds=elapsed,
            assumptions_made=assumptions,
            warnings=warnings,
            confidence_overall=confidence,
            building_regularity=regularity,
            recommended_review_items=self._review_items(
                supports=supports,
                gravity=gravity,
                lateral=lateral,
            ),
        )

        return StructuralDesignGraph(
            building_graph_id=graph_id,
            zones=zones,
            support_candidates=supports,
            forbidden_regions=forbidden,
            vertical_alignment_groups=vertical_groups,
            span_map=span_map,
            framing_zones=framing_zones,
            gravity_system_candidates=gravity,
            lateral_system_candidates=lateral,
            constraints=constraints,
            metadata=metadata,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _overall_confidence(*, supports, gravity, lateral, span_map) -> float:
        components: list[float] = []
        if supports:
            strong_frac = sum(1 for s in supports
                              if s.classification == SupportCandidateClass.STRONG) / len(supports)
            components.append(0.3 + 0.7 * strong_frac)
        if gravity:
            components.append(max(g.plausibility for g in gravity))
        if lateral:
            components.append(max(l.plausibility for l in lateral))
        if span_map.spans:
            components.append(span_map.span_regularity)
        if not components:
            return 0.0
        return sum(components) / len(components)

    @staticmethod
    def _regularity_label(reg: float) -> str:
        if reg >= 0.85:
            return "regular"
        if reg >= 0.70:
            return "mostly_regular"
        return "irregular"

    @staticmethod
    def _review_items(*, supports, gravity, lateral) -> list[str]:
        items: list[str] = []
        if supports:
            forbidden_count = sum(
                1 for s in supports if s.classification == SupportCandidateClass.FORBIDDEN
            )
            if forbidden_count:
                items.append(f"{forbidden_count} support candidates in forbidden regions")
        if gravity and gravity[0].plausibility < 0.5:
            items.append("No clearly plausible gravity system")
        if not lateral:
            items.append("No lateral system candidates generated")
        return items
