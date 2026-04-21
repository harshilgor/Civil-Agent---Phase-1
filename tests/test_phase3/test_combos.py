"""Tests for the LRFD load combination engine."""

from __future__ import annotations

import pytest

from src.phase3.engines.combos import evaluate_combinations
from src.phase3.models.enums import LoadCombinationType


def test_all_7_combinations_present():
    combos = evaluate_combinations(D=100, L=50, Lr=10, W=20, E=30)
    ids = {c.combination_id for c in combos}
    assert ids == set(LoadCombinationType)
    assert len(combos) == 7


def test_combination_1_is_1p4D():
    combos = evaluate_combinations(D=100.0, L=0, Lr=0, W=0, E=0)
    c1 = next(c for c in combos if c.combination_id == LoadCombinationType.LRFD_1)
    assert c1.factored_total == pytest.approx(140.0, rel=1e-9)


def test_governing_combination_flagged():
    combos = evaluate_combinations(D=100, L=50, Lr=10, W=20, E=30)
    governing = [c for c in combos if c.governs]
    assert len(governing) >= 1
    max_val = max(abs(c.factored_total) for c in combos)
    assert all(abs(g.factored_total) == max_val for g in governing)


def test_seismic_combo_uses_0p9D_for_uplift():
    combos = evaluate_combinations(D=100, L=0, Lr=0, W=0, E=-200)
    c7 = next(c for c in combos if c.combination_id == LoadCombinationType.LRFD_7)
    assert c7.factored_total == pytest.approx(0.9 * 100 + 1.0 * (-200), rel=1e-9)
