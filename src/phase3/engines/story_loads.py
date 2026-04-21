"""Story load aggregation engine.

Walks stories from roof to ground, accumulating dead, live, and seismic
weights. Per ASCE 7-22 Section 12.7.2, only 25 % of the live load is included
in the seismic effective weight for office / residential occupancies; for
storage occupancies 100 % is included.
"""

from __future__ import annotations

from typing import Any

from ..assumptions import AssumptionBuilder
from ..models.enums import OccupancyCategory
from ..models.loads import DeadLoadResult, LiveLoadResult, StoryLoadResult
from .live_load import _coerce_occupancy  # reuse string -> enum mapping

#: Default fraction of live load to include in the effective seismic weight.
#: 25 % for office / residential per ASCE 7-22 Section 12.7.2.
DEFAULT_SEISMIC_LIVE_FRACTION: float = 0.25

#: Full live load must be included for storage occupancies (SEI/ASCE 7-22 12.7.2).
STORAGE_SEISMIC_LIVE_FRACTION: float = 1.00


def compute_story_loads(
    building_graph: dict[str, Any],
    dead_loads: DeadLoadResult,
    live_loads: list[LiveLoadResult],
    assumption_builder: AssumptionBuilder,
) -> list[StoryLoadResult]:
    """Aggregate per-story dead and live loads and compute cumulative totals.

    Args:
        building_graph: Phase 1 BuildingGraph as a dict.
        dead_loads: The single DeadLoadResult produced by :mod:`dead_load`.
        live_loads: Unreduced live loads keyed by occupancy, one per occupancy.
        assumption_builder: Shared assumption builder.

    Returns:
        StoryLoadResults ordered from the highest roof story down to ground.
    """

    live_by_occupancy = {ll.occupancy: ll for ll in live_loads}
    stories = sorted(
        building_graph.get("stories") or [],
        key=lambda s: float(s.get("elevation_mm", 0.0)),
        reverse=True,
    )

    cumulative_dead_kN = 0.0
    cumulative_live_kN = 0.0
    results: list[StoryLoadResult] = []

    for story in stories:
        story_id = str(story.get("id"))
        elevation_m = float(story.get("elevation_mm", 0.0)) / 1000.0
        area_m2 = float(story.get("floor_area_gross_m2", 0.0))

        occupancy = _coerce_occupancy(story.get("usage")) or OccupancyCategory.OFFICE
        live = live_by_occupancy.get(occupancy)
        unreduced_live_kPa = live.unreduced_live_kPa if live else 0.0

        dead_kN = dead_loads.total_dead_kPa * area_m2
        live_kN = unreduced_live_kPa * area_m2

        live_fraction = _seismic_live_fraction(occupancy)
        weight_kN = dead_kN + live_fraction * live_kN

        cumulative_dead_kN += dead_kN
        cumulative_live_kN += live_kN

        fraction_id = f"seismic_weight_live_fraction_story_{story_id}"
        if not assumption_builder.has(fraction_id):
            assumption_builder.add(
                id=fraction_id,
                name=f"Seismic live-load fraction for story {story_id}",
                value=live_fraction,
                unit="dimensionless",
                source="ASCE 7-22 Section 12.7.2",
                confidence=0.92,
                rationale=(
                    "25 % of live load is included in the seismic effective weight for "
                    "office/residential occupancies; 100 % is included for storage."
                ),
                overrideable=True,
                affects_modules=["story_loads", "seismic"],
            )

        results.append(
            StoryLoadResult(
                story_id=story_id,
                elevation_m=elevation_m,
                floor_area_m2=area_m2,
                total_dead_kN=dead_kN,
                total_live_kN=live_kN,
                cumulative_dead_kN=cumulative_dead_kN,
                cumulative_live_kN=cumulative_live_kN,
                story_weight_kN=weight_kN,
                assumption_ids=[
                    fraction_id,
                    *dead_loads.assumption_ids,
                ],
            )
        )

    return results


def _seismic_live_fraction(occupancy: OccupancyCategory) -> float:
    """Return the live load fraction included in the seismic effective weight."""

    if occupancy in (OccupancyCategory.STORAGE_LIGHT, OccupancyCategory.STORAGE_HEAVY):
        return STORAGE_SEISMIC_LIVE_FRACTION
    return DEFAULT_SEISMIC_LIVE_FRACTION
