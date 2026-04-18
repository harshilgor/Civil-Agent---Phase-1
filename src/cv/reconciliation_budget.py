"""LLM reconciliation budget controller (Gap 9).

Prevents runaway LLM API costs when a floor plan is too degraded for
automated extraction. Two budgets are enforced simultaneously — the first
to trip wins:

  * **Absolute call cap:** ``MAX_LLM_CALLS`` (default 10).
  * **Proportional cap:** ``MAX_FRACTION_NEEDING_LLM`` (default 0.30) —
    once more than 30% of walls are waiting for LLM help, remaining walls
    are marked ``dimension_unknown`` with confidence 0.0.

When exiting reconciliation, if more than 30% of walls still have
``dimension_unknown``, the controller sets ``requires_human_review = True``
on the plan and adds a warning explaining why.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


MAX_LLM_CALLS = 10
MAX_FRACTION_NEEDING_LLM = 0.30
HUMAN_REVIEW_FRACTION = 0.30


@dataclass
class ReconciliationStats:
    """Collected over the lifetime of a single plan reconciliation."""

    llm_calls_made: int = 0
    llm_calls_successful: int = 0
    llm_calls_failed: int = 0
    llm_total_seconds: float = 0.0
    llm_estimated_cost_usd: float = 0.0
    walls_total: int = 0
    walls_unknown_final: int = 0
    requires_human_review: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_calls_made": self.llm_calls_made,
            "llm_calls_successful": self.llm_calls_successful,
            "llm_calls_failed": self.llm_calls_failed,
            "llm_total_seconds": round(self.llm_total_seconds, 3),
            "llm_estimated_cost_usd": round(self.llm_estimated_cost_usd, 4),
            "walls_total": self.walls_total,
            "walls_unknown_final": self.walls_unknown_final,
            "requires_human_review": self.requires_human_review,
            "warnings": self.warnings,
        }


class ReconciliationBudget:
    """Budget gatekeeper for LLM-based reconciliation calls."""

    # Rough pricing for Claude Sonnet vision per-image call (USD)
    APPROX_COST_PER_CALL = 0.015

    def __init__(
        self,
        max_calls: int = MAX_LLM_CALLS,
        max_fraction: float = MAX_FRACTION_NEEDING_LLM,
    ) -> None:
        self.max_calls = max_calls
        self.max_fraction = max_fraction
        self.stats = ReconciliationStats()

    def set_total_walls(self, n: int) -> None:
        self.stats.walls_total = n

    def allow_llm_call(self, walls_pending_llm: int) -> bool:
        """Return True if another LLM call is within both budgets."""
        if self.stats.walls_total == 0:
            return False
        fraction = walls_pending_llm / max(self.stats.walls_total, 1)
        if self.stats.llm_calls_made >= self.max_calls:
            logger.info("llm_budget_exhausted_absolute",
                        calls=self.stats.llm_calls_made, max=self.max_calls)
            return False
        if fraction > self.max_fraction:
            logger.info(
                "llm_budget_exhausted_fraction",
                pending=walls_pending_llm,
                total=self.stats.walls_total,
                fraction=round(fraction, 3),
            )
            return False
        return True

    def record(self, success: bool, duration_seconds: float) -> None:
        """Record the result of one LLM call."""
        self.stats.llm_calls_made += 1
        if success:
            self.stats.llm_calls_successful += 1
        else:
            self.stats.llm_calls_failed += 1
        self.stats.llm_total_seconds += duration_seconds
        self.stats.llm_estimated_cost_usd += self.APPROX_COST_PER_CALL

    def finalize(self, walls_unknown: int) -> ReconciliationStats:
        """Compute human-review flag based on remaining unknown walls."""
        self.stats.walls_unknown_final = walls_unknown
        if self.stats.walls_total == 0:
            return self.stats
        fraction_unknown = walls_unknown / self.stats.walls_total
        if fraction_unknown > HUMAN_REVIEW_FRACTION:
            self.stats.requires_human_review = True
            self.stats.warnings.append(
                f"Plan quality too low for automated dimension extraction. "
                f"{fraction_unknown:.0%} of walls have unknown dimensions. "
                f"Human review recommended."
            )
        return self.stats


# ---------------------------------------------------------------------------
# Convenience runner — wraps an LLM-callable with the budget controller
# ---------------------------------------------------------------------------


class BudgetedLLMReconciler:
    """Wraps any ``async`` LLM call with the budget controller.

    ``llm_fn`` must accept a ``wall`` dict and return ``(dimension_mm or None, confidence)``.
    """

    def __init__(self, llm_fn, budget: ReconciliationBudget | None = None) -> None:
        self._llm_fn = llm_fn
        self.budget = budget or ReconciliationBudget()

    async def resolve_walls(
        self, walls_needing_llm: list[dict[str, Any]], total_walls: int
    ) -> tuple[list[dict[str, Any]], ReconciliationStats]:
        """Attempt LLM reconciliation for each wall, respecting the budget.

        Returns the (possibly partially filled) wall list and the stats.
        Walls that exceed the budget are marked ``dimension_unknown`` with
        confidence 0.0.
        """
        self.budget.set_total_walls(total_walls)
        pending = len(walls_needing_llm)
        resolved: list[dict[str, Any]] = []

        for wall in walls_needing_llm:
            if not self.budget.allow_llm_call(pending):
                resolved.append({
                    **wall,
                    "dimension_mm": None,
                    "confidence": 0.0,
                    "dimension_unknown": True,
                    "reason": "llm_budget_exhausted",
                })
                continue

            t0 = time.perf_counter()
            try:
                dim_mm, conf = await self._llm_fn(wall)
                success = dim_mm is not None and dim_mm > 0
                self.budget.record(success, time.perf_counter() - t0)
                if success:
                    resolved.append({
                        **wall,
                        "dimension_mm": dim_mm,
                        "confidence": conf,
                        "dimension_unknown": False,
                    })
                else:
                    resolved.append({
                        **wall,
                        "dimension_mm": None,
                        "confidence": 0.0,
                        "dimension_unknown": True,
                        "reason": "llm_invalid_response",
                    })
            except Exception as exc:  # pragma: no cover
                self.budget.record(False, time.perf_counter() - t0)
                logger.warning("llm_reconciliation_error", error=str(exc))
                resolved.append({
                    **wall,
                    "dimension_mm": None,
                    "confidence": 0.0,
                    "dimension_unknown": True,
                    "reason": f"exception: {exc}",
                })
            pending -= 1

        walls_unknown_final = sum(1 for w in resolved if w.get("dimension_unknown"))
        stats = self.budget.finalize(walls_unknown_final)
        return resolved, stats


__all__ = [
    "BudgetedLLMReconciler",
    "HUMAN_REVIEW_FRACTION",
    "MAX_FRACTION_NEEDING_LLM",
    "MAX_LLM_CALLS",
    "ReconciliationBudget",
    "ReconciliationStats",
]
