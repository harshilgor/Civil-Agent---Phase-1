"""Tests for the ELF seismic engine."""

from __future__ import annotations

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.engines.dead_load import compute_dead_loads
from src.phase3.engines.live_load import compute_live_loads
from src.phase3.engines.seismic import (
    _distribution_exponent,
    compute_seismic_loads,
)
from src.phase3.engines.story_loads import compute_story_loads
from src.phase3.models.enums import MaterialFamily, RiskCategory


def _story_loads_fixture(bg):
    builder = AssumptionBuilder()
    d = compute_dead_loads(bg, MaterialFamily.REINFORCED_CONCRETE, builder)
    l = compute_live_loads(bg, builder)
    sl = compute_story_loads(bg, d, l, builder)
    return sl, builder


def test_sds_formula(sample_building_graph_office_rc, sample_structural_design_graph):
    sl, _ = _story_loads_fixture(sample_building_graph_office_rc)
    builder = AssumptionBuilder()
    result, _ = compute_seismic_loads(
        sample_building_graph_office_rc,
        sample_structural_design_graph,
        sl,
        material_family=MaterialFamily.REINFORCED_CONCRETE,
        risk_category=RiskCategory.II,
        site_class="D",
        Ss=1.0,
        S1=0.4,
        assumption_builder=builder,
    )
    assert result.SDS == pytest.approx((2.0 / 3.0) * result.Fa * 1.0, rel=1e-6)


def test_cs_bounded_by_max_and_min(
    sample_building_graph_office_rc, sample_structural_design_graph
):
    sl, _ = _story_loads_fixture(sample_building_graph_office_rc)
    builder = AssumptionBuilder()
    result, _ = compute_seismic_loads(
        sample_building_graph_office_rc,
        sample_structural_design_graph,
        sl,
        material_family=MaterialFamily.REINFORCED_CONCRETE,
        risk_category=RiskCategory.II,
        site_class="D",
        Ss=1.0,
        S1=0.4,
        assumption_builder=builder,
    )
    assert result.Cs > 0
    assert result.Cs >= 0.01  # absolute floor


def test_base_shear_formula(
    sample_building_graph_office_rc, sample_structural_design_graph
):
    sl, _ = _story_loads_fixture(sample_building_graph_office_rc)
    builder = AssumptionBuilder()
    result, _ = compute_seismic_loads(
        sample_building_graph_office_rc,
        sample_structural_design_graph,
        sl,
        material_family=MaterialFamily.REINFORCED_CONCRETE,
        risk_category=RiskCategory.II,
        site_class="D",
        Ss=1.0,
        S1=0.4,
        assumption_builder=builder,
    )
    assert result.V == pytest.approx(result.Cs * result.W, rel=1e-6)


def test_story_forces_sum_to_base_shear(
    sample_building_graph_office_rc, sample_structural_design_graph
):
    sl, _ = _story_loads_fixture(sample_building_graph_office_rc)
    builder = AssumptionBuilder()
    result, _ = compute_seismic_loads(
        sample_building_graph_office_rc,
        sample_structural_design_graph,
        sl,
        material_family=MaterialFamily.REINFORCED_CONCRETE,
        risk_category=RiskCategory.II,
        site_class="D",
        Ss=1.0,
        S1=0.4,
        assumption_builder=builder,
    )
    total = sum(result.story_forces.values())
    assert total == pytest.approx(result.V, rel=1e-6)


def test_sdc_D_triggers_elf_height_warning_if_above_50m(
    sample_building_graph_residential_steel, sample_structural_design_graph_residential
):
    # Force a tall building by multiplying total height.
    bg = dict(sample_building_graph_residential_steel)
    project = dict(bg["project"])
    project["total_height_mm"] = 60_000.0  # 60 m
    bg["project"] = project

    sl, _ = _story_loads_fixture(bg)
    builder = AssumptionBuilder()
    _, warnings = compute_seismic_loads(
        bg,
        sample_structural_design_graph_residential,
        sl,
        material_family=MaterialFamily.STRUCTURAL_STEEL,
        risk_category=RiskCategory.II,
        site_class="D",
        Ss=1.5,
        S1=0.6,  # high seismic -> SDC D
        assumption_builder=builder,
    )
    assert any(w.code == "P3W003" for w in warnings)


def test_k_interpolation_at_1p5_seconds():
    """Linear interpolation: k(1.5) = 1.0 + (1.5 - 0.5)/2 = 1.5."""

    assert _distribution_exponent(1.5) == pytest.approx(1.5, rel=1e-9)
    assert _distribution_exponent(0.5) == pytest.approx(1.0, rel=1e-9)
    assert _distribution_exponent(2.5) == pytest.approx(2.0, rel=1e-9)
    assert _distribution_exponent(0.3) == pytest.approx(1.0, rel=1e-9)
    assert _distribution_exponent(3.0) == pytest.approx(2.0, rel=1e-9)
