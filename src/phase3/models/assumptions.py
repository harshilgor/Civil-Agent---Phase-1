"""AssumptionRecord — re-export shim for the shared schema.

The canonical model lives in :mod:`src.schema.assumptions` so Phase 1 (Building
Graph) and Phase 3 (Load & Assumption Engine) share one definition.  This
module preserves the historical import path
``src.phase3.models.assumptions.AssumptionRecord`` for existing call sites.
"""

from __future__ import annotations

from src.schema.assumptions import AssumptionRecord

__all__ = ["AssumptionRecord"]
