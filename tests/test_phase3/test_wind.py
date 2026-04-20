"""Tests for the simplified wind engine."""

from __future__ import annotations

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.engines.wind import (
    EXPOSURE_PARAMETERS,
    KD_BUILDINGS,
    KZT_DEFAULT,
    compute_wind_loads,
)
from src.phase3.models.enums import ExposureCategory, RiskCategory


def test_kz_exposure_c_formula(sample_building_graph_office_rc):
    builder = AssumptionBuilder()
    result, _warnings = compute_wind_loads(
        sample_building_graph_office_rc,
        basic_wind_speed_m_per_s=40.0,
        exposure_category=ExposureCategory.C,
        risk_category=RiskCategory.II,
        assumption_builder=builder,
    )
    Kz_rec = builder.get("wind_velocity_pressure_coefficient_Kz")
    params = EXPOSURE_PARAMETERS[ExposureCategory.C]
    h = sample_building_graph_office_rc["project"]["total_height_mm"] / 1000.0
    expected = max(
        2.01 * (max(h, 4.6) / params["zg_m"]) ** (2.0 / params["alpha"]),
        params["kz_min"],
    )
    assert float(Kz_rec.value) == pytest.approx(expected, rel=1e-4)
    assert result.velocity_pressure_kPa > 0


def test_velocity_pressure_formula(sample_building_graph_office_rc):
    builder = AssumptionBuilder()
    V = 40.0
    result, _ = compute_wind_loads(
        sample_building_graph_office_rc,
        basic_wind_speed_m_per_s=V,
        exposure_category=ExposureCategory.C,
        risk_category=RiskCategory.II,
        assumption_builder=builder,
    )
    Kz = float(builder.get("wind_velocity_pressure_coefficient_Kz").value)
    expected_kPa = 0.613 * Kz * KZT_DEFAULT * KD_BUILDINGS * V * V / 1000.0
    assert result.velocity_pressure_kPa == pytest.approx(expected_kPa, rel=1e-4)


def test_net_lateral_wind_positive(sample_building_graph_office_rc):
    builder = AssumptionBuilder()
    result, _ = compute_wind_loads(
        sample_building_graph_office_rc,
        basic_wind_speed_m_per_s=40.0,
        exposure_category=ExposureCategory.C,
        risk_category=RiskCategory.II,
        assumption_builder=builder,
    )
    assert result.wind_base_shear_kN > 0


def test_story_forces_sum_to_base_shear(sample_building_graph_office_rc):
    builder = AssumptionBuilder()
    result, _ = compute_wind_loads(
        sample_building_graph_office_rc,
        basic_wind_speed_m_per_s=40.0,
        exposure_category=ExposureCategory.C,
        risk_category=RiskCategory.II,
        assumption_builder=builder,
    )
    total = sum(result.story_wind_forces.values())
    assert total == pytest.approx(result.wind_base_shear_kN, rel=1e-6)
