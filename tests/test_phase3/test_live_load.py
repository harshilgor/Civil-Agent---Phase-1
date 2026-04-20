"""Tests for the live load engine."""

from __future__ import annotations

import math

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.engines.live_load import (
    KLL_CORNER,
    KLL_EDGE,
    KLL_INTERIOR,
    LIVE_LOADS_KPA,
    compute_live_loads,
    reduce_live_load,
)
from src.phase3.models.enums import OccupancyCategory


def test_office_live_load_is_2p4_kPa(sample_building_graph_office_rc, empty_builder):
    results = compute_live_loads(sample_building_graph_office_rc, empty_builder)
    office = [r for r in results if r.occupancy == OccupancyCategory.OFFICE]
    assert office, "office occupancy must be present"
    assert office[0].unreduced_live_kPa == pytest.approx(2.40, rel=1e-6)


def test_residential_live_load_is_1p92_kPa(
    sample_building_graph_residential_steel, empty_builder
):
    results = compute_live_loads(sample_building_graph_residential_steel, empty_builder)
    res = [r for r in results if r.occupancy == OccupancyCategory.RESIDENTIAL]
    assert res, "residential occupancy must be present"
    assert res[0].unreduced_live_kPa == pytest.approx(1.92, rel=1e-6)


def test_storage_not_reduced(empty_builder):
    result = reduce_live_load(
        unreduced_live_kPa=LIVE_LOADS_KPA[OccupancyCategory.STORAGE_LIGHT],
        occupancy=OccupancyCategory.STORAGE_LIGHT,
        KLL=KLL_INTERIOR,
        tributary_area_m2=50.0,
        supports_multiple_floors=False,
        assumption_builder=empty_builder,
        support_id="S1",
    )
    assert result.reduction_applied is False
    assert result.reduction_factor == 1.0
    assert result.reduced_live_kPa == LIVE_LOADS_KPA[OccupancyCategory.STORAGE_LIGHT]


def test_live_load_reduction_formula(empty_builder):
    Lo = 2.40  # office
    AT = 40.0
    KLL = KLL_INTERIOR
    expected_factor = max(min(0.25 + 15.0 / math.sqrt(KLL * AT), 1.0), 0.50)

    result = reduce_live_load(
        unreduced_live_kPa=Lo,
        occupancy=OccupancyCategory.OFFICE,
        KLL=KLL,
        tributary_area_m2=AT,
        supports_multiple_floors=False,
        assumption_builder=empty_builder,
        support_id="S1",
    )
    assert result.reduction_factor == pytest.approx(expected_factor, rel=1e-6)
    assert result.reduced_live_kPa == pytest.approx(Lo * expected_factor, rel=1e-6)


def test_interior_column_kll_is_4():
    assert KLL_INTERIOR == 4.0


def test_corner_column_kll_is_1():
    assert KLL_CORNER == 1.0


def test_edge_column_kll_is_2():
    assert KLL_EDGE == 2.0


def test_minimum_reduction_applied(empty_builder):
    """For a very large tributary area, the floor of 0.40 L_o (multi-floor) applies."""

    Lo = 2.40
    result = reduce_live_load(
        unreduced_live_kPa=Lo,
        occupancy=OccupancyCategory.OFFICE,
        KLL=KLL_INTERIOR,
        tributary_area_m2=10_000.0,
        supports_multiple_floors=True,
        assumption_builder=empty_builder,
        support_id="Sbig",
    )
    assert result.reduction_factor == pytest.approx(0.40, rel=1e-6)
    assert result.reduced_live_kPa == pytest.approx(0.40 * Lo, rel=1e-6)
