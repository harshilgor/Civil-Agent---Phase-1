"""Dead load engine.

Computes dead loads per unit floor area (kPa) and the perimeter cladding
line load (kN/m) for the building, per ASCE 7-22 Chapter 3.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from ..assumptions import AssumptionBuilder
from ..models.enums import MaterialFamily
from ..models.loads import DeadLoadResult

#: Concrete unit weight (ASCE 7-22 Table C3.1-1). kN/m^3.
CONCRETE_UNIT_WEIGHT_KN_M3: float = 24.0

#: Default RC flat slab thickness in meters (common 2-way flat-slab assumption).
DEFAULT_RC_SLAB_THICKNESS_M: float = 0.200

#: Composite steel deck + concrete fill unit dead load (AISC Design Guide 3).
COMPOSITE_DECK_SELF_WEIGHT_KPA: float = 3.0

#: Default superimposed dead load for office/residential (floor finishes, ceilings).
DEFAULT_SDL_KPA: float = 1.0

#: Superimposed dead load for mechanical floors (equipment + housekeeping pads).
MECHANICAL_SDL_KPA: float = 2.0

#: Mechanical / electrical / plumbing allowance for typical floors.
DEFAULT_MEP_ALLOWANCE_KPA: float = 0.5

#: Partition dead-load allowance per ASCE 7-22 Section 4.3.2 (≥1.0 kPa treated as dead).
DEFAULT_PARTITION_LOAD_KPA: float = 1.0

#: Typical unitised curtain wall weight per meter of perimeter per floor.
DEFAULT_CLADDING_KN_PER_M: float = 1.5


def compute_dead_loads(
    building_graph: dict[str, Any],
    material_family: MaterialFamily,
    assumption_builder: AssumptionBuilder,
) -> DeadLoadResult:
    """Compute dead loads for the building.

    Args:
        building_graph: Phase 1 BuildingGraph serialized to a dict.
        material_family: Primary structural material family.
        assumption_builder: Shared assumption builder for the run.

    Returns:
        A populated :class:`DeadLoadResult`.
    """

    assumption_ids: list[str] = []

    self_weight_kPa = _structural_self_weight(
        material_family, assumption_builder, assumption_ids
    )
    sdl_kPa = _superimposed_dead(assumption_builder, assumption_ids)
    mep_kPa = _mep_allowance(assumption_builder, assumption_ids)
    partitions_kPa = _partition_load(
        building_graph, assumption_builder, assumption_ids
    )
    cladding_kN_per_m = _cladding_line_load(
        building_graph, assumption_builder, assumption_ids
    )

    total_dead_kPa = self_weight_kPa + sdl_kPa + mep_kPa + partitions_kPa

    return DeadLoadResult(
        structural_self_weight_kPa=self_weight_kPa,
        superimposed_dead_kPa=sdl_kPa,
        mep_allowance_kPa=mep_kPa,
        partitions_kPa=partitions_kPa,
        cladding_kN_per_m=cladding_kN_per_m,
        total_dead_kPa=total_dead_kPa,
        assumption_ids=assumption_ids,
    )


def _structural_self_weight(
    material_family: MaterialFamily,
    builder: AssumptionBuilder,
    ids: list[str],
) -> float:
    """Return the structural slab self-weight in kPa and record assumptions."""

    if material_family == MaterialFamily.REINFORCED_CONCRETE:
        thickness_m = DEFAULT_RC_SLAB_THICKNESS_M
        builder.add(
            id="slab_thickness_rc",
            name="RC flat slab thickness",
            value=thickness_m,
            unit="m",
            source="Common RC 2-way flat-slab practice (200 mm default)",
            confidence=0.80,
            rationale=(
                "No explicit slab thickness provided; using a 200 mm RC flat slab "
                "as a conservative default typical for office/residential bays ~8–9 m."
            ),
            overrideable=True,
            affects_modules=["dead_load", "story_loads", "seismic"],
        )
        ids.append("slab_thickness_rc")

        unit_weight = CONCRETE_UNIT_WEIGHT_KN_M3
        builder.add(
            id="concrete_unit_weight",
            name="Reinforced concrete unit weight",
            value=unit_weight,
            unit="kN/m^3",
            source="ASCE 7-22 Table C3.1-1",
            confidence=0.98,
            rationale="Normal-weight reinforced concrete unit weight.",
            overrideable=True,
            affects_modules=["dead_load", "story_loads", "seismic"],
        )
        ids.append("concrete_unit_weight")

        self_weight = thickness_m * unit_weight
        builder.add(
            id="slab_self_weight_rc",
            name="RC slab self-weight",
            value=round(self_weight, 3),
            unit="kPa",
            source="ASCE 7-22 Table C3.1-1 x slab thickness",
            confidence=0.90,
            rationale=(
                f"Self-weight = {thickness_m} m x {unit_weight} kN/m^3 = {self_weight:.2f} kPa "
                "for a 200 mm RC flat slab."
            ),
            overrideable=True,
            affects_modules=["dead_load", "story_loads", "seismic"],
        )
        ids.append("slab_self_weight_rc")
        return self_weight

    if material_family == MaterialFamily.STRUCTURAL_STEEL:
        self_weight = COMPOSITE_DECK_SELF_WEIGHT_KPA
        builder.add(
            id="slab_self_weight_steel",
            name="Composite deck slab self-weight",
            value=self_weight,
            unit="kPa",
            source="AISC Design Guide 3, composite deck typical values",
            confidence=0.88,
            rationale=(
                "130 mm total composite slab (~80 mm NWC topping on 50 mm steel deck); "
                "industry-standard self-weight of ~3.0 kPa."
            ),
            overrideable=True,
            affects_modules=["dead_load", "story_loads", "seismic"],
        )
        ids.append("slab_self_weight_steel")
        return self_weight

    raise ValueError(f"Unsupported material family for dead load: {material_family}")


def _superimposed_dead(builder: AssumptionBuilder, ids: list[str]) -> float:
    """Record and return the superimposed dead load in kPa."""

    builder.add(
        id="superimposed_dead_load",
        name="Superimposed dead load (floor finishes, ceilings)",
        value=DEFAULT_SDL_KPA,
        unit="kPa",
        source="Industry-typical SDL for office/residential floors",
        confidence=0.80,
        rationale=(
            "Floor finishes, ceilings, light MEP routing; override to 2.0 kPa for "
            "mechanical levels or to a project-specific value when finishes schedule is known."
        ),
        overrideable=True,
        affects_modules=["dead_load", "story_loads", "seismic", "combos"],
    )
    ids.append("superimposed_dead_load")
    return DEFAULT_SDL_KPA


def _mep_allowance(builder: AssumptionBuilder, ids: list[str]) -> float:
    """Record and return the MEP allowance in kPa."""

    builder.add(
        id="mep_allowance",
        name="Mechanical / electrical / plumbing allowance",
        value=DEFAULT_MEP_ALLOWANCE_KPA,
        unit="kPa",
        source="Engineering practice (non-structural dead allowance)",
        confidence=0.80,
        rationale="Generic MEP hanging-load allowance; override when trade coordination data exists.",
        overrideable=True,
        affects_modules=["dead_load", "story_loads", "seismic", "combos"],
    )
    ids.append("mep_allowance")
    return DEFAULT_MEP_ALLOWANCE_KPA


def _partition_load(
    building_graph: dict[str, Any],
    builder: AssumptionBuilder,
    ids: list[str],
) -> float:
    """Record and return the partition dead allowance in kPa per ASCE 7-22 4.3.2."""

    occupancy = _project_occupancy(building_graph)
    applies = occupancy in {"office", "residential", "mixed_use", None}
    value = DEFAULT_PARTITION_LOAD_KPA if applies else 0.0

    builder.add(
        id="partition_load",
        name="Partition dead allowance",
        value=value,
        unit="kPa",
        source="ASCE 7-22 Section 4.3.2",
        confidence=0.90,
        rationale=(
            "ASCE 7-22 Section 4.3.2 requires at least 1.0 kPa partition allowance for "
            "office/residential; treated as dead when >= 1.0 kPa."
        ),
        overrideable=True,
        affects_modules=["dead_load", "story_loads", "combos"],
    )
    ids.append("partition_load")
    return value


def _cladding_line_load(
    building_graph: dict[str, Any],
    builder: AssumptionBuilder,
    ids: list[str],
) -> float:
    """Record and return the cladding line load in kN per meter of perimeter."""

    perimeter_m = _facade_perimeter_m(building_graph)
    if perimeter_m <= 0:
        from ..warnings import WARNING_CODES  # local import to avoid cycle

        _ = WARNING_CODES  # keep import for clarity (warnings generated upstream)

    builder.add(
        id="cladding_unit_weight",
        name="Cladding weight per meter of perimeter per floor",
        value=DEFAULT_CLADDING_KN_PER_M,
        unit="kN/m",
        source="Industry-typical unitised curtain wall (1.0–2.0 kN/m range)",
        confidence=0.75,
        rationale=(
            "Conservative estimate for unitised curtain wall; overrides strongly "
            "recommended once cladding type is selected."
        ),
        overrideable=True,
        affects_modules=["dead_load", "story_loads", "combos"],
    )
    ids.append("cladding_unit_weight")

    builder.add(
        id="facade_perimeter_length",
        name="Facade perimeter length",
        value=round(perimeter_m, 3),
        unit="m",
        source="Shapely perimeter of building_graph.facade.perimeter_polygon",
        confidence=0.95 if perimeter_m > 0 else 0.10,
        rationale=(
            "Computed directly from the facade polygon. Cladding line load is applied to "
            "perimeter columns only."
        ),
        overrideable=True,
        affects_modules=["dead_load"],
    )
    ids.append("facade_perimeter_length")

    return DEFAULT_CLADDING_KN_PER_M


def _project_occupancy(building_graph: dict[str, Any]) -> str | None:
    """Return the project-level occupancy string, or ``None`` if missing."""

    project = building_graph.get("project") or {}
    value = project.get("occupancy_type")
    if value is None:
        return None
    return str(value).lower()


def _facade_perimeter_m(building_graph: dict[str, Any]) -> float:
    """Compute the facade perimeter in meters using Shapely.

    Building Graph coordinates are in millimeters; converts to meters on output.
    Returns 0.0 if the facade polygon is missing or degenerate.
    """

    facade = building_graph.get("facade") or {}
    poly_pts = facade.get("perimeter_polygon") or []
    if len(poly_pts) < 3:
        return 0.0
    try:
        polygon = Polygon(poly_pts)
        if not polygon.is_valid or polygon.is_empty:
            return 0.0
        # Shapely returns length in the same units as coordinates (mm -> m).
        return float(polygon.exterior.length) / 1000.0
    except (ValueError, TypeError):
        return 0.0
