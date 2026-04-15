"""Route light vs deep fusion based on pipeline mode."""

from __future__ import annotations

from typing import Any

from ..core.schemas import PipelineMode


class FusionRouter:
    def __init__(self, mode: PipelineMode) -> None:
        self.mode = mode

    def fuse(self, perception: Any) -> Any:
        if self.mode == PipelineMode.LIGHT:
            from .light.light_fusion import light_fuse

            return light_fuse(perception)
        from .deep.boundary_fusion import fuse_boundaries
        from .deep.room_fusion import fuse_rooms

        # Orchestrator assembles sub-stages; placeholder
        b = fuse_boundaries(perception)
        r = fuse_rooms(perception)
        return {"boundaries": b, "rooms": r}
