"""Gravity system eligibility evaluator.

For each gravity system rule (defined in ``config.GRAVITY_SYSTEM_RULES``),
computes a plausibility score given the current span map and
material preference. Outputs ``GravitySystemCandidate`` entries.
"""

from __future__ import annotations

import logging

from src.schema.building_graph import BuildingGraph
from src.schema.enums import MaterialPreference
from src.schema.structural_enums import GravitySystemType
from src.schema.structural_graph import GravitySystemCandidate, SpanMap
from src.structural.config import GRAVITY_SYSTEM_RULES, StructuralConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class GravitySystemEligibilityEvaluator:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def evaluate(
        self,
        graph: BuildingGraph,
        span_map: SpanMap,
    ) -> list[GravitySystemCandidate]:
        if not span_map.spans:
            return []

        out: list[GravitySystemCandidate] = []
        material = graph.project.material_preference

        # Only emit RC systems if material is RC or COMPOSITE, steel systems
        # are handled separately (not in V1 rules).
        for system_key, rule in GRAVITY_SYSTEM_RULES.items():
            if material == MaterialPreference.STRUCTURAL_STEEL:
                continue  # RC-only systems for V1

            limitations: list[str] = []
            plaus = 1.0

            # Span range
            if span_map.max_span_mm > rule.max_span_mm:
                excess = span_map.max_span_mm - rule.max_span_mm
                plaus *= max(0.0, 1.0 - excess / rule.max_span_mm)
                limitations.append(
                    f"max_span {span_map.max_span_mm:.0f}mm > allowed {rule.max_span_mm:.0f}mm"
                )
            if span_map.min_span_mm < rule.min_span_mm:
                plaus *= 0.85
                limitations.append(
                    f"some spans below {rule.min_span_mm:.0f}mm"
                )

            # Aspect ratio
            if span_map.spans:
                max_aspect = max(s.aspect_ratio for s in span_map.spans)
                if max_aspect > rule.max_aspect_ratio:
                    plaus *= 0.7
                    limitations.append(f"aspect ratio {max_aspect:.2f} exceeds {rule.max_aspect_ratio}")
                if max_aspect < rule.min_aspect_ratio:
                    plaus *= 0.7
                    limitations.append(
                        f"aspect ratio {max_aspect:.2f} below {rule.min_aspect_ratio}"
                    )

            # Regularity
            # span_regularity is (1 - cv); cv = 1 - regularity
            cv = max(0.0, 1.0 - span_map.span_regularity)
            if cv > rule.regularity_required:
                plaus *= max(0.2, 1.0 - (cv - rule.regularity_required))
                limitations.append(f"irregularity cv={cv:.2f} > {rule.regularity_required}")

            plaus = max(0.0, min(1.0, plaus))
            system_type = GravitySystemType[system_key]

            rationale = self._rationale(system_type, span_map, plaus)
            out.append(
                GravitySystemCandidate(
                    system_type=system_type,
                    plausibility=plaus,
                    applicable_zones=[],
                    rationale=rationale,
                    limitations=limitations,
                )
            )

        out.sort(key=lambda c: c.plausibility, reverse=True)
        return out

    @staticmethod
    def _rationale(system: GravitySystemType, span_map: SpanMap, plaus: float) -> str:
        verdict = "plausible" if plaus >= 0.5 else "marginal" if plaus >= 0.2 else "poor fit"
        return (
            f"{system.value} is {verdict}: typical span "
            f"{span_map.typical_span_mm:.0f}mm, max {span_map.max_span_mm:.0f}mm, "
            f"regularity {span_map.span_regularity:.2f}"
        )
