"""Tests for the AssumptionBuilder registry."""

from __future__ import annotations

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.models.inputs import OverrideEntry
from src.phase3.phase3_service import Phase3Service


def test_every_computed_value_has_assumption_record(sample_phase3_input_office_rc):
    output = Phase3Service().run(sample_phase3_input_office_rc)
    register = output.assumption_register
    # Must cover the major calculation constants.
    required = {
        "slab_self_weight_rc",
        "superimposed_dead_load",
        "mep_allowance",
        "partition_load",
        "cladding_unit_weight",
        "basic_wind_speed",
        "wind_velocity_pressure_qz",
        "seismic_Ss",
        "seismic_S1",
        "seismic_Cs",
        "seismic_effective_weight_W",
        "load_combination_standard",
    }
    assert required.issubset({r.id for r in register.records})
    assert register.total_count >= 20


def test_override_non_overrideable_raises():
    builder = AssumptionBuilder()
    builder.add(
        id="locked",
        name="Locked assumption",
        value=1.0,
        unit="kPa",
        source="test",
        confidence=0.9,
        rationale="test",
        overrideable=False,
        affects_modules=[],
    )
    with pytest.raises(ValueError):
        builder.apply_overrides([OverrideEntry(assumption_id="locked", new_value=2.0)])


def test_override_updates_record():
    builder = AssumptionBuilder()
    builder.add(
        id="open",
        name="Open assumption",
        value=1.0,
        unit="kPa",
        source="test",
        confidence=0.8,
        rationale="test",
        overrideable=True,
        affects_modules=[],
    )
    builder.apply_overrides([OverrideEntry(assumption_id="open", new_value=3.0)])
    rec = builder.get("open")
    assert rec.was_overridden
    assert rec.effective_value == 3.0


def test_register_counts_correct():
    builder = AssumptionBuilder()
    for i in range(3):
        builder.add(
            id=f"a{i}",
            name=f"a{i}",
            value=1.0,
            unit=None,
            source="test",
            confidence=0.55 if i < 1 else 0.95,
            rationale="test",
            overrideable=True,
            affects_modules=[],
        )
    builder.apply_overrides([OverrideEntry(assumption_id="a0", new_value=2.0)])
    register = builder.build_register()
    assert register.total_count == 3
    assert register.overridden_count == 1
    assert register.low_confidence_count == 1
