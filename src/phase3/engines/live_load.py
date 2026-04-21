"""Live load engine.

Assigns unreduced live loads per occupancy category (ASCE 7-22 Table 4.3-1)
and exposes the ASCE 7-22 Section 4.7.3 live load reduction formula.
"""

from __future__ import annotations

import math
from typing import Any

from ..assumptions import AssumptionBuilder
from ..models.enums import OccupancyCategory
from ..models.loads import LiveLoadResult

#: Embedded ASCE 7-22 Table 4.3-1 live loads (unreduced), in kPa.
#: Converted from psf with 1 psf = 0.0479 kPa.
LIVE_LOADS_KPA: dict[OccupancyCategory, float] = {
    OccupancyCategory.OFFICE: 2.40,            # 50 psf
    OccupancyCategory.RESIDENTIAL: 1.92,       # 40 psf
    OccupancyCategory.RETAIL: 4.79,            # 100 psf
    OccupancyCategory.STORAGE_LIGHT: 6.00,     # 125 psf
    OccupancyCategory.STORAGE_HEAVY: 12.00,    # 250 psf
    OccupancyCategory.ASSEMBLY: 4.79,          # 100 psf
    OccupancyCategory.MECHANICAL: 3.83,        # 80 psf
    OccupancyCategory.ROOF_ACCESSIBLE: 1.92,   # 40 psf
    OccupancyCategory.ROOF_INACCESSIBLE: 0.96, # 20 psf
    OccupancyCategory.PARKING: 2.40,           # 50 psf
    OccupancyCategory.CORRIDOR: 4.79,          # 100 psf
    OccupancyCategory.LOBBY: 4.79,             # 100 psf
}

#: Occupancies for which live load reduction is NOT permitted
#: (per ASCE 7-22 Section 4.7.3 and 4.7.6).
NON_REDUCIBLE_OCCUPANCIES: frozenset[OccupancyCategory] = frozenset(
    {
        OccupancyCategory.STORAGE_LIGHT,
        OccupancyCategory.STORAGE_HEAVY,
        OccupancyCategory.ASSEMBLY,
    }
)

#: Live-load-element factor K_LL per ASCE 7-22 Table 4.7-1.
KLL_INTERIOR: float = 4.0
KLL_EDGE: float = 2.0
KLL_CORNER: float = 1.0

#: Upper-bound unreduced live load for which LL reduction is permitted.
#: Beyond this value (storage and similar heavy uses) reduction is NOT allowed.
REDUCTION_UPPER_LIMIT_KPA: float = 4.79  # 100 psf

#: Minimum reduction factor when supporting a single floor.
MIN_FACTOR_SINGLE_FLOOR: float = 0.50

#: Minimum reduction factor when supporting two or more floors.
MIN_FACTOR_MULTI_FLOOR: float = 0.40


def compute_live_loads(
    building_graph: dict[str, Any],
    assumption_builder: AssumptionBuilder,
) -> list[LiveLoadResult]:
    """Return unreduced live loads for each unique occupancy in the building.

    Args:
        building_graph: Phase 1 BuildingGraph serialized to a dict.
        assumption_builder: Shared assumption builder.

    Returns:
        List with one :class:`LiveLoadResult` per distinct occupancy referenced
        in the building's stories. Each result carries the unreduced live load;
        reduction factors are applied per support in :func:`reduce_live_load`.
    """

    occupancies = _collect_occupancies(building_graph)
    results: list[LiveLoadResult] = []

    for occ in occupancies:
        unreduced = LIVE_LOADS_KPA[occ]
        assumption_id = f"live_load_unreduced_{occ.value}"
        if not assumption_builder.has(assumption_id):
            assumption_builder.add(
                id=assumption_id,
                name=f"Unreduced live load for {occ.value}",
                value=unreduced,
                unit="kPa",
                source="ASCE 7-22 Table 4.3-1",
                confidence=0.95,
                rationale=f"Table 4.3-1 minimum uniformly distributed live load for {occ.value}.",
                overrideable=True,
                affects_modules=["live_load", "story_loads", "combos", "seismic"],
            )

        results.append(
            LiveLoadResult(
                occupancy=occ,
                unreduced_live_kPa=unreduced,
                reduction_factor=1.0,
                reduced_live_kPa=unreduced,
                reduction_applied=False,
                reduction_rationale=(
                    "Unreduced value. Per-support reduction is applied downstream "
                    "via the 0.25 + 15/sqrt(KLL*AT) formula."
                ),
                assumption_ids=[assumption_id],
            )
        )

    return results


def reduce_live_load(
    *,
    unreduced_live_kPa: float,
    occupancy: OccupancyCategory,
    KLL: float,
    tributary_area_m2: float,
    supports_multiple_floors: bool,
    assumption_builder: AssumptionBuilder,
    support_id: str,
) -> LiveLoadResult:
    """Apply the ASCE 7-22 Section 4.7.3 live load reduction formula.

    Formula::

        L = L_o * (0.25 + 15 / sqrt(KLL * A_T))

    with floors of ``0.50 L_o`` (one floor) or ``0.40 L_o`` (two or more).

    Reduction is not permitted for storage or assembly occupancies; in those
    cases the returned result echoes the unreduced value and sets
    ``reduction_applied=False``.

    Args:
        unreduced_live_kPa: ``L_o`` — unreduced live load from Table 4.3-1.
        occupancy: Occupancy category, used to check eligibility for reduction.
        KLL: Live load element factor (4 interior / 2 edge / 1 corner).
        tributary_area_m2: ``A_T`` — tributary area in square meters.
        supports_multiple_floors: Whether the supporting member carries two or
            more floors (affects the minimum reduction floor).
        assumption_builder: Shared assumption builder (records the per-support
            reduction factor).
        support_id: Support id being reduced (used to name the assumption).

    Returns:
        A :class:`LiveLoadResult` for this (support, occupancy).
    """

    if unreduced_live_kPa < 0:
        raise ValueError("unreduced_live_kPa must be non-negative")
    if tributary_area_m2 <= 0:
        raise ValueError("tributary_area_m2 must be positive for live load reduction")
    if KLL <= 0:
        raise ValueError("KLL must be positive")

    reduction_allowed = _reduction_allowed(occupancy, unreduced_live_kPa)
    if not reduction_allowed:
        return LiveLoadResult(
            occupancy=occupancy,
            unreduced_live_kPa=unreduced_live_kPa,
            reduction_factor=1.0,
            reduced_live_kPa=unreduced_live_kPa,
            reduction_applied=False,
            reduction_rationale=(
                f"Reduction not permitted for occupancy '{occupancy.value}' or L_o exceeds "
                f"{REDUCTION_UPPER_LIMIT_KPA} kPa (ASCE 7-22 Section 4.7.3)."
            ),
            support_id=support_id,
            assumption_ids=[],
        )

    raw_factor = 0.25 + 15.0 / math.sqrt(KLL * tributary_area_m2)
    floor = MIN_FACTOR_MULTI_FLOOR if supports_multiple_floors else MIN_FACTOR_SINGLE_FLOOR
    factor = max(min(raw_factor, 1.0), floor)
    reduced = unreduced_live_kPa * factor

    assumption_id = f"live_load_reduction_factor_{support_id}"
    if not assumption_builder.has(assumption_id):
        assumption_builder.add(
            id=assumption_id,
            name=f"Live load reduction factor for {support_id}",
            value=round(factor, 4),
            unit="dimensionless",
            source="ASCE 7-22 Section 4.7.3",
            confidence=0.92,
            rationale=(
                f"L/L_o = max(min(0.25 + 15/sqrt({KLL}*{tributary_area_m2:.2f}), 1.0), "
                f"{floor}) = {factor:.3f}."
            ),
            overrideable=False,
            affects_modules=["live_load", "combos", "member_demands"],
        )

    return LiveLoadResult(
        occupancy=occupancy,
        unreduced_live_kPa=unreduced_live_kPa,
        reduction_factor=factor,
        reduced_live_kPa=reduced,
        reduction_applied=True,
        reduction_rationale=(
            f"L = L_o * (0.25 + 15/sqrt(KLL*A_T)) with KLL={KLL} and A_T={tributary_area_m2:.2f} m^2; "
            f"result clipped to floor of {floor:.2f} L_o."
        ),
        support_id=support_id,
        assumption_ids=[assumption_id],
    )


def _reduction_allowed(occupancy: OccupancyCategory, unreduced_kPa: float) -> bool:
    """Return True if live load reduction is permitted for this occupancy."""

    if occupancy in NON_REDUCIBLE_OCCUPANCIES:
        return False
    if unreduced_kPa > REDUCTION_UPPER_LIMIT_KPA:
        return False
    return True


def _collect_occupancies(building_graph: dict[str, Any]) -> list[OccupancyCategory]:
    """Return unique occupancy categories referenced by the building graph."""

    collected: list[OccupancyCategory] = []
    seen: set[OccupancyCategory] = set()

    for story in building_graph.get("stories") or []:
        usage = story.get("usage")
        occ = _coerce_occupancy(usage)
        if occ is not None and occ not in seen:
            collected.append(occ)
            seen.add(occ)

    if not collected:
        # Fall back to the project-level occupancy when per-story usage is missing.
        project = building_graph.get("project") or {}
        occ = _coerce_occupancy(project.get("occupancy_type"))
        if occ is not None:
            collected.append(occ)

    if not collected:
        collected.append(OccupancyCategory.OFFICE)
    return collected


def _coerce_occupancy(value: Any) -> OccupancyCategory | None:
    """Best-effort mapping from free-form usage/occupancy strings to enum."""

    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in OccupancyCategory._value2member_map_:
        return OccupancyCategory(text)
    mapping = {
        "office_building": OccupancyCategory.OFFICE,
        "residential_building": OccupancyCategory.RESIDENTIAL,
        "apartment": OccupancyCategory.RESIDENTIAL,
        "apartments": OccupancyCategory.RESIDENTIAL,
        "house": OccupancyCategory.RESIDENTIAL,
        "retail_store": OccupancyCategory.RETAIL,
        "shop": OccupancyCategory.RETAIL,
        "warehouse": OccupancyCategory.STORAGE_LIGHT,
        "storage": OccupancyCategory.STORAGE_LIGHT,
        "garage": OccupancyCategory.PARKING,
        "hall": OccupancyCategory.ASSEMBLY,
        "auditorium": OccupancyCategory.ASSEMBLY,
        "mechanical_room": OccupancyCategory.MECHANICAL,
        "roof": OccupancyCategory.ROOF_INACCESSIBLE,
        "mixed_use": OccupancyCategory.OFFICE,
    }
    return mapping.get(text)
