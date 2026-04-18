"""Structural constraint compiler.

Emits ``StructuralConstraint`` objects that downstream optimization must
respect.  Each constraint has a type, an optional region / story, a
value, and priority (hard vs soft).
"""

from __future__ import annotations

import logging

from src.schema.building_graph import BuildingGraph
from src.schema.structural_enums import (
    ConstraintPriority,
    ConstraintType,
    StructuralZoneType,
)
from src.schema.structural_graph import (
    ForbiddenRegion,
    LateralSystemCandidate,
    SpanMap,
    StructuralConstraint,
    StructuralZone,
    SupportCandidate,
    VerticalAlignmentGroup,
)
from src.structural.config import DEFAULT_CONFIG, StructuralConfig

logger = logging.getLogger(__name__)


class ConstraintCompiler:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def compile(
        self,
        *,
        graph: BuildingGraph,
        zones: list[StructuralZone],
        support_candidates: list[SupportCandidate],
        forbidden_regions: list[ForbiddenRegion],
        vertical_groups: list[VerticalAlignmentGroup],
        span_map: SpanMap,
        lateral_candidates: list[LateralSystemCandidate],
    ) -> list[StructuralConstraint]:
        out: list[StructuralConstraint] = []
        idx = 0

        def add(**kw) -> None:
            nonlocal idx
            kw.setdefault("id", f"c-{idx}")
            idx += 1
            out.append(StructuralConstraint(**kw))

        # 1. Forbidden regions → NO_SUPPORT_ZONE (hard)
        for fr in forbidden_regions:
            add(
                type=ConstraintType.NO_SUPPORT_ZONE,
                region=fr.polygon,
                story=fr.story,
                priority=ConstraintPriority.HARD,
                source=f"forbidden_region:{fr.id}",
                rationale=f"{fr.reason.value}: {fr.notes}",
            )

        # 2. Required supports (STRONG + is_stacked) → REQUIRED_SUPPORT (hard)
        strong_stacked = [c for c in support_candidates
                          if c.is_stacked and c.score >= self.config.supports.strong_threshold]
        for c in strong_stacked[:50]:  # cap
            add(
                type=ConstraintType.REQUIRED_SUPPORT,
                region=[c.position],
                story=c.story,
                priority=ConstraintPriority.HARD,
                source=f"support:{c.id}",
                rationale=f"Strong stacked support (score={c.score:.2f})",
            )

        # 3. Span limits
        if span_map.max_span_mm > 0:
            add(
                type=ConstraintType.MAX_SPAN_LIMIT,
                value=self.config.supports.rc_max_span_mm,
                priority=ConstraintPriority.HARD,
                source="material_limits",
                rationale=f"Max allowable RC span {self.config.supports.rc_max_span_mm:.0f}mm",
            )
            add(
                type=ConstraintType.MIN_SPAN_LIMIT,
                value=2_500.0,
                priority=ConstraintPriority.SOFT,
                source="economy",
                rationale="Spans below 2.5m are uneconomical",
            )

        # 4. Corridor clearance
        for zone in zones:
            if zone.type == StructuralZoneType.CORRIDOR_BAND:
                add(
                    type=ConstraintType.CORRIDOR_CLEARANCE,
                    region=zone.polygon,
                    story=zone.story,
                    value=self.config.zoning.narrow_corridor_width_mm,
                    priority=ConstraintPriority.HARD,
                    source=f"zone:{zone.id}",
                    rationale="Corridor must remain clear",
                )

        # 5. Vertical alignment
        for grp in vertical_groups:
            if grp.alignment_quality > 0.6:
                add(
                    type=ConstraintType.VERTICAL_ALIGNMENT_REQUIRED,
                    priority=ConstraintPriority.SOFT,
                    source=f"vag:{grp.id}",
                    rationale=f"Preserve stacking (quality {grp.alignment_quality:.2f})",
                )
            if grp.has_transfer:
                add(
                    type=ConstraintType.TRANSFER_AVOIDANCE,
                    story=grp.transfer_story,
                    priority=ConstraintPriority.SOFT,
                    source=f"vag:{grp.id}",
                    rationale="Transfer detected — avoid if possible",
                )

        # 6. Opening avoidance
        for o in graph.openings:
            if o.width_mm >= 2_000:
                add(
                    type=ConstraintType.OPENING_AVOIDANCE,
                    value=o.width_mm,
                    priority=ConstraintPriority.SOFT,
                    source=f"opening:{o.id}",
                    rationale="Large opening — no column directly adjacent",
                )

        # 7. Facade setback
        if graph.facade.perimeter_polygon:
            add(
                type=ConstraintType.FACADE_SETBACK,
                region=graph.facade.perimeter_polygon,
                priority=ConstraintPriority.SOFT,
                value=300.0,
                source="facade",
                rationale="Columns recessed from facade by 300mm",
            )

        # 8. Core continuity
        for zone in zones:
            if zone.type == StructuralZoneType.CORE_SERVICE:
                add(
                    type=ConstraintType.CORE_CONTINUITY,
                    region=zone.polygon,
                    story=zone.story,
                    priority=ConstraintPriority.HARD,
                    source=f"zone:{zone.id}",
                    rationale="Core must run through all stories",
                )

        # 9. Lateral system requirement
        if lateral_candidates:
            strongest = lateral_candidates[0]
            add(
                type=ConstraintType.LATERAL_SYSTEM_REQUIRED,
                region=strongest.polygon,
                value=strongest.plausibility,
                priority=ConstraintPriority.HARD,
                source=f"lateral:{strongest.system_type.value}",
                rationale=f"At least one lateral system of type "
                          f"{strongest.system_type.value} required",
            )

        return out
