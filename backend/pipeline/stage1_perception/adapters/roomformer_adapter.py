"""RoomFormer: density map from boundary fusion (256×256), polygon extraction."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("roomformer")
class RoomFormerAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load vendors/roomformer checkpoint.")

    def predict(self, density_map: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Single-channel 256×256 density map input.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(roomformer_polygons=[])
