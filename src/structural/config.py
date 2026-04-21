"""Tunable thresholds for the Structural Abstraction Engine (Phase 2).

All magic numbers from the algorithm specification live here so they can be
adjusted without touching algorithm code.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Zoning thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoningConfig:
    # Cluster cores when their centroids are within this distance
    core_cluster_distance_mm: float = 5_000.0
    # Corridor below this width is "narrow" → no-support-zone
    narrow_corridor_width_mm: float = 2_500.0
    # Room above this area with no interior walls is an open floor plate
    open_plate_min_area_m2: float = 100.0
    # High-clearance ratio trigger
    high_clearance_multiplier: float = 1.5
    # Min area difference (m²) between ground floor and upper floors for transfer risk
    transfer_risk_ground_floor_delta_m2: float = 200.0
    # Facade adjacency: rooms are "perimeter" if their polygon shares an
    # edge with the facade within this tolerance (mm)
    facade_adjacency_tolerance_mm: float = 500.0


# ---------------------------------------------------------------------------
# Support scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupportConfig:
    base_score_grid_intersection: float = 0.70
    base_score_wall_intersection: float = 0.60
    base_score_core_corner: float = 0.85
    base_score_perimeter_corner: float = 0.90
    base_score_midspan: float = 0.50

    # Grid alignment — distance from grid intersection (mm)
    grid_align_within_mm: float = 500.0
    grid_align_decay_at_mm: float = 2_000.0

    # Tributary area (m²) band
    tributary_area_sweet_min_m2: float = 30.0
    tributary_area_sweet_max_m2: float = 80.0
    tributary_area_absurd_min_m2: float = 10.0
    tributary_area_absurd_max_m2: float = 150.0

    # Max span before midspan support is inserted (mm)
    rc_max_span_mm: float = 12_000.0
    steel_max_span_mm: float = 15_000.0

    # Class thresholds
    strong_threshold: float = 0.80
    secondary_threshold: float = 0.50
    weak_threshold: float = 0.20

    # Forbidden region buffers (mm)
    elevator_buffer_mm: float = 500.0
    stair_buffer_mm: float = 300.0
    corridor_centerline_band_mm: float = 1_000.0


# ---------------------------------------------------------------------------
# Vertical continuity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerticalContinuityConfig:
    match_tolerance_mm: float = 500.0
    perfect_stack_bonus: float = 0.15
    partial_stack_bonus_per_floor: float = 0.05
    isolated_penalty: float = -0.10
    transfer_floor_drop_fraction: float = 0.30


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpanConfig:
    square_aspect_max: float = 1.5
    elongated_aspect_max: float = 2.5
    # Regularity thresholds (stddev/mean of spans)
    regular_max_cv: float = 0.15
    mostly_regular_max_cv: float = 0.30


# ---------------------------------------------------------------------------
# Framing directions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FramingConfig:
    bay_aspect_weight: float = 0.40
    wall_continuity_weight: float = 0.25
    core_placement_weight: float = 0.20
    corridor_orientation_weight: float = 0.15
    bidirectional_aspect_max: float = 1.15


# ---------------------------------------------------------------------------
# Gravity systems (RC-only for V1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GravitySystemEligibility:
    min_span_mm: float
    max_span_mm: float
    max_aspect_ratio: float = 10.0
    min_aspect_ratio: float = 1.0
    regularity_required: float = 0.30  # spans/regularity must be <= this
    occupancy_ok: tuple[str, ...] = ()


GRAVITY_SYSTEM_RULES: dict[str, GravitySystemEligibility] = {
    "RC_FLAT_SLAB": GravitySystemEligibility(
        min_span_mm=5_000, max_span_mm=9_000, regularity_required=0.20,
    ),
    "RC_BEAM_SLAB": GravitySystemEligibility(
        min_span_mm=6_000, max_span_mm=14_000, regularity_required=0.40,
    ),
    "RC_ONE_WAY_SLAB": GravitySystemEligibility(
        min_span_mm=3_000, max_span_mm=8_000, min_aspect_ratio=1.5,
    ),
    "RC_TWO_WAY_SLAB": GravitySystemEligibility(
        min_span_mm=5_000, max_span_mm=10_000, max_aspect_ratio=1.3,
    ),
    "POST_TENSIONED_SLAB": GravitySystemEligibility(
        min_span_mm=8_000, max_span_mm=15_000, regularity_required=0.25,
    ),
}


# ---------------------------------------------------------------------------
# Lateral systems
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LateralConfig:
    core_centered_bonus: float = 0.10
    min_shear_wall_length_mm: float = 3_000.0
    min_braced_frame_bay_mm: float = 3_000.0
    max_braced_frame_bay_mm: float = 9_000.0


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralConfig:
    zoning: ZoningConfig = ZoningConfig()
    supports: SupportConfig = SupportConfig()
    vertical: VerticalContinuityConfig = VerticalContinuityConfig()
    spans: SpanConfig = SpanConfig()
    framing: FramingConfig = FramingConfig()
    lateral: LateralConfig = LateralConfig()


DEFAULT_CONFIG = StructuralConfig()
