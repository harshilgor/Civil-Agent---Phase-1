"""TF2 DeepFloorplan: subprocess or isolated TF session; 512×512, BGR→RGB."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import ModelBoundaryOutput, ModelRoomOutput, UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("deepfloorplan")
class DeepFloorplanAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load TF2 model in subprocess or isolated session.")

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Forward to 512×512; optional dfp.deploy colorize.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(
            deepfloorplan_rooms=ModelRoomOutput(),
            deepfloorplan_boundaries=ModelBoundaryOutput(),
        )
