"""Stage-1 perception; lazy export avoids import cycles with `single_model_run` + `registry`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .perception_orchestrator import PerceptionOrchestrator

__all__ = ["PerceptionOrchestrator"]


def __getattr__(name: str) -> Any:
    if name == "PerceptionOrchestrator":
        from .perception_orchestrator import PerceptionOrchestrator as _Orchestrator

        return _Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
