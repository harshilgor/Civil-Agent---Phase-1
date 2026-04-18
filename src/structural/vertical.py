"""Vertical continuity analyzer.

Detects groups of support candidates that stack vertically across stories
and adjusts their scores. Detects potential transfer conditions when a
lower story has significantly different column layout than upper stories.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from src.schema.building_graph import BuildingGraph
from src.schema.structural_enums import SupportCandidateClass, SupportCandidateReason
from src.schema.structural_graph import SupportCandidate, VerticalAlignmentGroup
from src.structural.config import DEFAULT_CONFIG, StructuralConfig

logger = logging.getLogger(__name__)


class VerticalContinuityAnalyzer:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def analyze(
        self,
        candidates: list[SupportCandidate],
        graph: BuildingGraph,
    ) -> tuple[list[SupportCandidate], list[VerticalAlignmentGroup]]:
        cfg = self.config.vertical
        ordered_stories = sorted(graph.stories, key=lambda s: s.level)
        story_levels = {s.id: s.level for s in ordered_stories}

        by_story: dict[str, list[SupportCandidate]] = defaultdict(list)
        for c in candidates:
            by_story[c.story].append(c)

        # Bucket by (x, y) rounded to tolerance
        tol = cfg.match_tolerance_mm
        buckets: dict[tuple[int, int], list[SupportCandidate]] = defaultdict(list)
        for c in candidates:
            key = (round(c.position[0] / tol), round(c.position[1] / tol))
            buckets[key].append(c)

        groups: list[VerticalAlignmentGroup] = []
        support_to_group: dict[str, str] = {}
        total_stories = len(ordered_stories)

        for idx, (_, group) in enumerate(buckets.items()):
            stories_present = {c.story for c in group}
            if len(stories_present) < 2:
                if total_stories >= 2 and len(group) == 1:
                    # Apply isolated penalty
                    c = group[0]
                    c.score = max(0.0, min(1.0, c.score + cfg.isolated_penalty))
                    self._reclassify(c)
                continue

            coverage = len(stories_present) / total_stories
            bonus = cfg.perfect_stack_bonus if coverage >= 0.95 else (
                cfg.partial_stack_bonus_per_floor * len(stories_present)
            )

            # Detect transfer
            levels_present = sorted(story_levels[s] for s in stories_present)
            has_transfer = levels_present[0] > 1  # missing ground floor
            transfer_story = None
            if has_transfer and ordered_stories:
                transfer_story = next(
                    (s.id for s in ordered_stories if s.level == levels_present[0]),
                    None,
                )

            group_id = f"vag-{idx}"
            for c in group:
                c.score = max(0.0, min(1.0, c.score + bonus))
                c.is_stacked = True
                c.stack_group_id = group_id
                if has_transfer:
                    c.score = max(0.0, c.score - cfg.transfer_floor_drop_fraction * c.score)
                support_to_group[c.id] = group_id
                self._reclassify(c)

            # Compute offset and alignment quality
            xs = [c.position[0] for c in group]
            ys = [c.position[1] for c in group]
            offset = max(
                max(xs) - min(xs),
                max(ys) - min(ys),
            )
            alignment_quality = max(0.0, 1.0 - offset / max(tol, 1e-6))

            groups.append(
                VerticalAlignmentGroup(
                    id=group_id,
                    support_ids=[c.id for c in group],
                    stories=sorted(stories_present),
                    alignment_quality=alignment_quality,
                    offset_mm=offset,
                    has_transfer=has_transfer,
                    transfer_story=transfer_story,
                )
            )

        return candidates, groups

    def _reclassify(self, c: SupportCandidate) -> None:
        cfg = self.config.supports
        if c.classification == SupportCandidateClass.FORBIDDEN:
            return
        if c.score >= cfg.strong_threshold:
            c.classification = SupportCandidateClass.STRONG
        elif c.score >= cfg.secondary_threshold:
            c.classification = SupportCandidateClass.SECONDARY
        else:
            c.classification = SupportCandidateClass.WEAK
