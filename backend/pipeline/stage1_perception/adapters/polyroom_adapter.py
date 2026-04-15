"""PolyRoom: Mask2Former on density map, then polygon refinement."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("polyroom")
class PolyRoomAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load PolyRoom + Mask2Former deps.")

    def predict(self, density_map: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Two-phase instance seg + refinement.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(polyroom_polygons=[])
