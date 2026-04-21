"""Tests for override injection and re-execution."""

from __future__ import annotations

import pytest

from src.phase3.models.inputs import OverrideEntry
from src.phase3.overrides import inject_overrides
from src.phase3.phase3_service import Phase3Service


def test_inject_overrides_merges(sample_phase3_input_office_rc):
    base = sample_phase3_input_office_rc
    merged = inject_overrides(
        base,
        [OverrideEntry(assumption_id="superimposed_dead_load", new_value=2.0)],
    )
    assert len(merged.overrides) == len(base.overrides) + 1
    assert merged.overrides[-1].assumption_id == "superimposed_dead_load"


def test_rerun_with_overrides_applies(sample_phase3_input_office_rc):
    service = Phase3Service()
    updated = service.rerun_with_overrides(
        sample_phase3_input_office_rc,
        [OverrideEntry(assumption_id="superimposed_dead_load", new_value=2.0)],
    )
    rec = updated.assumption_register.get_by_id("superimposed_dead_load")
    assert rec is not None
    assert rec.was_overridden is True
    assert rec.effective_value == 2.0
