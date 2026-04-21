"""LRFD load combination engine per ASCE 7-22 Section 2.3.1.

Evaluates all seven strength-level combinations at each support candidate on
each story, flagging the governing combination. Snow (S) and rain (R) are
assumed zero unless the caller supplies overrides via the assumption register.
"""

from __future__ import annotations

from typing import Iterable

from ..assumptions import AssumptionBuilder
from ..models.enums import LoadCombinationType, OccupancyCategory
from ..models.loads import (
    DeadLoadResult,
    LiveLoadResult,
    LoadCombinationResult,
    MemberLoadDemand,
    SeismicLoadResult,
    StoryLoadResult,
    TributaryAreaResult,
    WindLoadResult,
)
from .live_load import LIVE_LOADS_KPA, reduce_live_load, _coerce_occupancy

#: Label -> combination id
COMBINATION_LABELS: dict[LoadCombinationType, str] = {
    LoadCombinationType.LRFD_1: "1.4D",
    LoadCombinationType.LRFD_2: "1.2D + 1.6L + 0.5Lr",
    LoadCombinationType.LRFD_3: "1.2D + 1.6Lr + 0.5W",
    LoadCombinationType.LRFD_4: "1.2D + 1.0W + 1.0L + 0.5Lr",
    LoadCombinationType.LRFD_5: "0.9D + 1.0W",
    LoadCombinationType.LRFD_6: "1.2D + 1.0E + 1.0L",
    LoadCombinationType.LRFD_7: "0.9D + 1.0E",
}


def evaluate_combinations(
    *,
    D: float,
    L: float,
    Lr: float,
    W: float,
    E: float,
    assumption_ids: list[str] | None = None,
) -> list[LoadCombinationResult]:
    """Evaluate all seven LRFD load combinations for a single component.

    Returns:
        A list of 7 :class:`LoadCombinationResult` objects with the governing
        combination flagged (maximum factored_total).
    """

    aids = assumption_ids or []

    raw: list[tuple[LoadCombinationType, float]] = [
        (LoadCombinationType.LRFD_1, 1.4 * D),
        (LoadCombinationType.LRFD_2, 1.2 * D + 1.6 * L + 0.5 * Lr),
        (LoadCombinationType.LRFD_3, 1.2 * D + 1.6 * Lr + 0.5 * W),
        (LoadCombinationType.LRFD_4, 1.2 * D + 1.0 * W + 1.0 * L + 0.5 * Lr),
        (LoadCombinationType.LRFD_5, 0.9 * D + 1.0 * W),
        (LoadCombinationType.LRFD_6, 1.2 * D + 1.0 * E + 1.0 * L),
        (LoadCombinationType.LRFD_7, 0.9 * D + 1.0 * E),
    ]

    max_total = max((abs(total) for _, total in raw), default=0.0)

    return [
        LoadCombinationResult(
            combination_id=combo_id,
            combination_label=COMBINATION_LABELS[combo_id],
            D=D,
            L=L,
            Lr=Lr,
            W=W,
            E=E,
            factored_total=total,
            governs=(abs(total) == max_total and max_total > 0),
            assumption_ids=list(aids),
        )
        for combo_id, total in raw
    ]


def compute_member_demands(
    *,
    tributary_areas: list[TributaryAreaResult],
    story_loads: list[StoryLoadResult],
    dead_loads: DeadLoadResult,
    live_loads: list[LiveLoadResult],
    wind_loads: WindLoadResult,
    seismic_loads: SeismicLoadResult,
    building_graph: dict,
    assumption_builder: AssumptionBuilder,
) -> tuple[list[MemberLoadDemand], list[LoadCombinationResult]]:
    """Compute per-support axial demands and a representative combination set.

    Returns:
        Tuple of (per-member demands, all-seven combinations evaluated at the
        support that produced the worst factored axial demand — this is the
        representative result surfaced on DesignLoadModel.load_combinations).
    """

    assumption_builder.add(
        id="load_combination_standard",
        name="LRFD load combination set",
        value="ASCE 7-22 Section 2.3.1",
        unit=None,
        source="ASCE 7-22 Section 2.3.1",
        confidence=0.99,
        rationale="Strength-level LRFD combinations (1–7).",
        overrideable=False,
        affects_modules=["combos", "member_demands"],
    )

    live_by_occ = {ll.occupancy: ll for ll in live_loads}
    story_meta = {
        str(s.get("id")): s for s in building_graph.get("stories") or []
    }

    story_totals_weight = {sl.story_id: sl.floor_area_m2 for sl in story_loads}
    story_wind = wind_loads.story_wind_forces
    story_seismic = seismic_loads.story_forces

    story_order = [sl.story_id for sl in story_loads]  # roof -> ground
    story_position = {sid: i for i, sid in enumerate(story_order)}

    demands: list[MemberLoadDemand] = []
    cumulative: dict[str, float] = {}  # per-support running axial

    for trib in sorted(
        tributary_areas,
        key=lambda t: story_position.get(t.story_id, 10_000),
    ):
        support_id = trib.support_id
        story_id = trib.story_id
        story_dict = story_meta.get(story_id) or {}
        occupancy = _coerce_occupancy(story_dict.get("usage")) or OccupancyCategory.OFFICE
        unreduced_live_kPa = LIVE_LOADS_KPA.get(occupancy, 2.4)

        KLL = _KLL_for(trib)
        supports_multi = story_position.get(story_id, 0) < len(story_order) - 1
        live_reduced = reduce_live_load(
            unreduced_live_kPa=unreduced_live_kPa,
            occupancy=occupancy,
            KLL=KLL,
            tributary_area_m2=trib.tributary_area_m2,
            supports_multiple_floors=supports_multi,
            assumption_builder=assumption_builder,
            support_id=f"{support_id}__{story_id}",
        )

        axial_D = dead_loads.total_dead_kPa * trib.tributary_area_m2
        axial_L = live_reduced.reduced_live_kPa * trib.tributary_area_m2
        axial_Lr = (
            LIVE_LOADS_KPA[OccupancyCategory.ROOF_INACCESSIBLE] * trib.tributary_area_m2
            if occupancy in (
                OccupancyCategory.ROOF_ACCESSIBLE,
                OccupancyCategory.ROOF_INACCESSIBLE,
            )
            else 0.0
        )

        total_story_area = story_totals_weight.get(story_id, 1.0) or 1.0
        area_fraction = trib.tributary_area_m2 / total_story_area
        axial_W = story_wind.get(story_id, 0.0) * area_fraction
        axial_E = story_seismic.get(story_id, 0.0) * area_fraction

        combos_here = evaluate_combinations(
            D=axial_D, L=axial_L, Lr=axial_Lr, W=axial_W, E=axial_E,
            assumption_ids=["load_combination_standard"],
        )
        governing = max(combos_here, key=lambda c: abs(c.factored_total))

        cumulative[support_id] = cumulative.get(support_id, 0.0) + governing.factored_total

        demands.append(
            MemberLoadDemand(
                support_id=support_id,
                story_id=story_id,
                axial_dead_kN=axial_D,
                axial_live_kN=axial_L,
                axial_factored_kN=governing.factored_total,
                governing_combination=governing.combination_id,
                cumulative_axial_kN=cumulative[support_id],
                assumption_ids=[
                    "load_combination_standard",
                    *live_reduced.assumption_ids,
                ],
            )
        )

    # Representative 7-combination result: the worst-case support
    if demands:
        worst = max(demands, key=lambda d: abs(d.axial_factored_kN))
        representative = _representative_combinations(
            worst=worst,
            tributary_areas=tributary_areas,
            live_loads=live_loads,
            dead_loads=dead_loads,
            wind_loads=wind_loads,
            seismic_loads=seismic_loads,
            building_graph=building_graph,
            story_totals_weight=story_totals_weight,
        )
    else:
        # No tributary areas — fall back to building-scale totals (W only available).
        total_D = sum(sl.total_dead_kN for sl in story_loads)
        total_L = sum(sl.total_live_kN for sl in story_loads)
        representative = evaluate_combinations(
            D=total_D, L=total_L, Lr=0.0,
            W=wind_loads.wind_base_shear_kN, E=seismic_loads.V,
            assumption_ids=["load_combination_standard"],
        )

    return demands, representative


def _KLL_for(trib: TributaryAreaResult) -> float:
    """Map the classification flags to the live-load element factor K_LL."""

    if trib.is_corner_column:
        return 1.0
    if trib.is_edge_column:
        return 2.0
    return 4.0


def _representative_combinations(
    *,
    worst: MemberLoadDemand,
    tributary_areas: list[TributaryAreaResult],
    live_loads: Iterable[LiveLoadResult],
    dead_loads: DeadLoadResult,
    wind_loads: WindLoadResult,
    seismic_loads: SeismicLoadResult,
    building_graph: dict,
    story_totals_weight: dict[str, float],
) -> list[LoadCombinationResult]:
    """Re-run all 7 combinations at the governing support (for visibility)."""

    trib = next(
        (t for t in tributary_areas
         if t.support_id == worst.support_id and t.story_id == worst.story_id),
        None,
    )
    if trib is None:
        return evaluate_combinations(
            D=worst.axial_dead_kN, L=worst.axial_live_kN, Lr=0.0,
            W=0.0, E=0.0,
            assumption_ids=["load_combination_standard"],
        )

    story_dict = next(
        (s for s in building_graph.get("stories") or [] if s.get("id") == worst.story_id),
        {},
    )
    occupancy = _coerce_occupancy(story_dict.get("usage")) or OccupancyCategory.OFFICE
    axial_Lr = (
        LIVE_LOADS_KPA[OccupancyCategory.ROOF_INACCESSIBLE] * trib.tributary_area_m2
        if occupancy in (
            OccupancyCategory.ROOF_ACCESSIBLE,
            OccupancyCategory.ROOF_INACCESSIBLE,
        )
        else 0.0
    )
    total_story_area = story_totals_weight.get(worst.story_id, 1.0) or 1.0
    area_fraction = trib.tributary_area_m2 / total_story_area
    axial_W = wind_loads.story_wind_forces.get(worst.story_id, 0.0) * area_fraction
    axial_E = seismic_loads.story_forces.get(worst.story_id, 0.0) * area_fraction

    return evaluate_combinations(
        D=worst.axial_dead_kN,
        L=worst.axial_live_kN,
        Lr=axial_Lr,
        W=axial_W,
        E=axial_E,
        assumption_ids=["load_combination_standard"],
    )
