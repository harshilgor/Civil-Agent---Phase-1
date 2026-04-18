"""Tests for LLM reconciliation budget (Gap 9)."""

from __future__ import annotations

import asyncio

import pytest

from src.cv.reconciliation_budget import (
    HUMAN_REVIEW_FRACTION,
    MAX_FRACTION_NEEDING_LLM,
    MAX_LLM_CALLS,
    BudgetedLLMReconciler,
    ReconciliationBudget,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Unit tests — ReconciliationBudget
# ---------------------------------------------------------------------------


def test_allow_llm_when_under_budget() -> None:
    b = ReconciliationBudget()
    b.set_total_walls(100)
    assert b.allow_llm_call(walls_pending_llm=10) is True


def test_reject_llm_when_over_absolute_budget() -> None:
    b = ReconciliationBudget(max_calls=3)
    b.set_total_walls(100)
    for _ in range(3):
        b.record(success=True, duration_seconds=0.1)
    assert b.allow_llm_call(walls_pending_llm=10) is False


def test_reject_llm_when_over_fractional_budget() -> None:
    b = ReconciliationBudget()
    b.set_total_walls(10)
    # 5/10 = 50% > 30% fraction cap
    assert b.allow_llm_call(walls_pending_llm=5) is False


def test_finalize_flags_human_review() -> None:
    b = ReconciliationBudget()
    b.set_total_walls(10)
    stats = b.finalize(walls_unknown=5)
    assert stats.requires_human_review is True
    assert any("Human review" in w for w in stats.warnings)


def test_finalize_no_human_review_when_mostly_resolved() -> None:
    b = ReconciliationBudget()
    b.set_total_walls(10)
    stats = b.finalize(walls_unknown=1)
    assert stats.requires_human_review is False


def test_stats_to_dict_roundtrip() -> None:
    b = ReconciliationBudget()
    b.set_total_walls(10)
    b.record(True, 0.5)
    d = b.stats.to_dict()
    assert d["llm_calls_made"] == 1
    assert d["walls_total"] == 10


# ---------------------------------------------------------------------------
# Integration — BudgetedLLMReconciler
# ---------------------------------------------------------------------------


def test_reconciler_respects_absolute_budget() -> None:
    async def fake_llm(wall):
        return 6000.0, 0.9

    # 20 walls all "needing LLM" with a max of 10 calls
    walls = [{"id": f"w-{i}"} for i in range(20)]
    reconciler = BudgetedLLMReconciler(fake_llm, budget=ReconciliationBudget(max_calls=10))
    resolved, stats = _run(reconciler.resolve_walls(walls, total_walls=20))
    # Budget will also kick in on fraction (20/20 = 100% > 30%) so 0 calls succeed
    assert stats.llm_calls_made <= 10
    assert len(resolved) == 20


def test_reconciler_makes_up_to_budget_when_fraction_ok() -> None:
    async def fake_llm(wall):
        return 6000.0, 0.9

    # 100 walls total, 10 need LLM (10% — under 30% cap)
    walls = [{"id": f"w-{i}"} for i in range(10)]
    reconciler = BudgetedLLMReconciler(fake_llm, budget=ReconciliationBudget(max_calls=10))
    resolved, stats = _run(reconciler.resolve_walls(walls, total_walls=100))
    assert stats.llm_calls_made == 10
    assert stats.llm_calls_successful == 10
    assert all(not r.get("dimension_unknown") for r in resolved)


def test_degraded_plan_flagged_for_human_review() -> None:
    async def fake_llm(wall):
        return 6000.0, 0.9

    # 50% of walls need LLM — the fractional cap (30%) is exceeded immediately,
    # so budget shuts down all calls, leaving walls unresolved.
    walls = [{"id": f"w-{i}"} for i in range(50)]
    reconciler = BudgetedLLMReconciler(fake_llm, budget=ReconciliationBudget())
    resolved, stats = _run(reconciler.resolve_walls(walls, total_walls=100))
    # Walls resolved = fewer than 10 because fraction cap kicks in
    unknown = sum(1 for r in resolved if r.get("dimension_unknown"))
    # Stats should reflect a substantial unknown set
    assert unknown > 0
    # When 50 unresolved + 50 resolved in total_walls=100, unknown fraction ≈ 50% > 30%
    # So human-review should be flagged
    assert stats.walls_unknown_final == unknown
    if stats.walls_unknown_final / stats.walls_total > HUMAN_REVIEW_FRACTION:
        assert stats.requires_human_review is True


def test_reconciler_records_failed_calls() -> None:
    async def fake_llm(wall):
        return None, 0.0  # invalid LLM response

    walls = [{"id": f"w-{i}"} for i in range(5)]
    reconciler = BudgetedLLMReconciler(fake_llm, budget=ReconciliationBudget())
    resolved, stats = _run(reconciler.resolve_walls(walls, total_walls=100))
    assert stats.llm_calls_failed == 5
    assert stats.llm_calls_successful == 0


def test_default_thresholds() -> None:
    assert MAX_LLM_CALLS == 10
    assert MAX_FRACTION_NEEDING_LLM == 0.30
    assert HUMAN_REVIEW_FRACTION == 0.30
