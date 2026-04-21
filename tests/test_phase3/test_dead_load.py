"""Tests for the dead load engine."""

from __future__ import annotations

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.engines.dead_load import (
    CONCRETE_UNIT_WEIGHT_KN_M3,
    DEFAULT_CLADDING_KN_PER_M,
    DEFAULT_MEP_ALLOWANCE_KPA,
    DEFAULT_PARTITION_LOAD_KPA,
    DEFAULT_RC_SLAB_THICKNESS_M,
    DEFAULT_SDL_KPA,
    compute_dead_loads,
)
from src.phase3.models.enums import MaterialFamily
from src.phase3.models.inputs import OverrideEntry


def test_rc_slab_self_weight_correct(
    sample_building_graph_office_rc, empty_builder: AssumptionBuilder
):
    result = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, empty_builder
    )
    expected = DEFAULT_RC_SLAB_THICKNESS_M * CONCRETE_UNIT_WEIGHT_KN_M3
    assert result.structural_self_weight_kPa == pytest.approx(expected, rel=1e-6)
    assert result.structural_self_weight_kPa == pytest.approx(4.8, rel=1e-6)


def test_steel_deck_self_weight_correct(
    sample_building_graph_residential_steel, empty_builder: AssumptionBuilder
):
    result = compute_dead_loads(
        sample_building_graph_residential_steel,
        MaterialFamily.STRUCTURAL_STEEL,
        empty_builder,
    )
    assert result.structural_self_weight_kPa == pytest.approx(3.0, rel=1e-6)


def test_total_dead_load_is_sum_of_components(
    sample_building_graph_office_rc, empty_builder: AssumptionBuilder
):
    result = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, empty_builder
    )
    total = (
        result.structural_self_weight_kPa
        + result.superimposed_dead_kPa
        + result.mep_allowance_kPa
        + result.partitions_kPa
    )
    assert result.total_dead_kPa == pytest.approx(total, rel=1e-9)


def test_all_assumptions_recorded(
    sample_building_graph_office_rc, empty_builder: AssumptionBuilder
):
    compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, empty_builder
    )
    register = empty_builder.build_register()
    required = {
        "slab_thickness_rc",
        "concrete_unit_weight",
        "slab_self_weight_rc",
        "superimposed_dead_load",
        "mep_allowance",
        "partition_load",
        "cladding_unit_weight",
        "facade_perimeter_length",
    }
    registered = {r.id for r in register.records}
    assert required.issubset(registered)
    for r in register.records:
        assert r.source


def test_override_superimposed_dead(
    sample_building_graph_office_rc, empty_builder: AssumptionBuilder
):
    compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, empty_builder
    )
    empty_builder.apply_overrides(
        [OverrideEntry(assumption_id="superimposed_dead_load", new_value=1.5)]
    )
    rec = empty_builder.get("superimposed_dead_load")
    assert rec.was_overridden is True
    assert rec.effective_value == 1.5


def test_cladding_uses_perimeter_length(
    sample_building_graph_office_rc, empty_builder: AssumptionBuilder
):
    result = compute_dead_loads(
        sample_building_graph_office_rc, MaterialFamily.REINFORCED_CONCRETE, empty_builder
    )
    assert result.cladding_kN_per_m == pytest.approx(DEFAULT_CLADDING_KN_PER_M)
    perimeter_rec = empty_builder.get("facade_perimeter_length")
    expected_perimeter_m = 2 * (4 * 9.0 + 3 * 8.0)  # width + depth in meters, x2
    assert perimeter_rec.value == pytest.approx(expected_perimeter_m, rel=1e-6)


def test_default_constants_match_spec():
    assert DEFAULT_SDL_KPA == 1.0
    assert DEFAULT_MEP_ALLOWANCE_KPA == 0.5
    assert DEFAULT_PARTITION_LOAD_KPA == 1.0
