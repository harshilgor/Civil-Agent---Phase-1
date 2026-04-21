"""Override application.

The simplest and safest way to apply user overrides is to re-run the pipeline
with the overrides inserted into the assumption builder before the engines
execute. This module exposes a helper that does exactly that, plus a
lighter-weight in-place patcher for fast subset overrides.
"""

from __future__ import annotations

from .models.inputs import OverrideEntry, Phase3Input


def inject_overrides(phase3_input: Phase3Input, overrides: list[OverrideEntry]) -> Phase3Input:
    """Return a new :class:`Phase3Input` with the overrides appended.

    Used by the orchestrator and by :func:`rerun_with_overrides` in the API
    layer. The new payload carries both the previous and new overrides so that
    the downstream engines use the merged list.
    """

    merged = list(phase3_input.overrides) + list(overrides)
    return phase3_input.model_copy(update={"overrides": merged})
