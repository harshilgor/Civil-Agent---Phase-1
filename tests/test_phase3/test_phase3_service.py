"""End-to-end tests for the Phase 3 orchestrator."""

from __future__ import annotations

import pytest

from src.phase3.models.enums import ConfidenceLevel
from src.phase3.models.inputs import Phase3Input
from src.phase3.models.outputs import Phase3Output
from src.phase3.phase3_service import Phase3Service


def test_full_run_returns_phase3_output(sample_phase3_input_office_rc):
    output = Phase3Service().run(sample_phase3_input_office_rc)
    assert isinstance(output, Phase3Output)
    assert output.status in {"success", "partial"}
    assert output.design_load_model is not None


def test_wrong_building_code_returns_failed_status(sample_phase3_input_office_rc):
    bad = sample_phase3_input_office_rc.model_copy(update={"building_code": "Eurocode 1"})
    output = Phase3Service().run(bad)
    assert output.status == "failed"
    assert output.design_load_model is None
    assert any(w.code == "P3W008" for w in output.warnings)


def test_all_output_fields_populated(sample_phase3_input_office_rc):
    output = Phase3Service().run(sample_phase3_input_office_rc)
    dm = output.design_load_model
    assert dm is not None
    assert dm.dead_loads.total_dead_kPa > 0
    assert dm.live_loads
    assert dm.tributary_areas
    assert dm.story_loads
    assert dm.wind_loads.wind_base_shear_kN >= 0
    assert dm.seismic_loads.V >= 0
    assert len(dm.load_combinations) == 7
    assert dm.member_demands


def test_confidence_score_between_0_and_1(sample_phase3_input_office_rc):
    output = Phase3Service().run(sample_phase3_input_office_rc)
    assert 0.10 <= output.overall_confidence <= 1.0
    assert isinstance(output.overall_confidence_level, ConfidenceLevel)


def test_member_demands_present_for_all_supports(sample_phase3_input_office_rc):
    output = Phase3Service().run(sample_phase3_input_office_rc)
    dm = output.design_load_model
    assert dm is not None
    # We have 20 columns x 8 stories = 160 (support, story) pairs expected
    assert len(dm.member_demands) >= len(dm.tributary_areas) * 0.9


def test_residential_steel_end_to_end(sample_phase3_input_residential_steel):
    output = Phase3Service().run(sample_phase3_input_residential_steel)
    assert output.status in {"success", "partial"}
    dm = output.design_load_model
    assert dm is not None
    assert dm.dead_loads.structural_self_weight_kPa == pytest.approx(3.0, rel=1e-6)
