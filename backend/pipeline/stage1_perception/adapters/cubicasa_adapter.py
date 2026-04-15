"""CubiCasa: resize, 4-rotation TTA, split_prediction → room + boundary outputs."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import ModelBoundaryOutput, ModelRoomOutput, UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("cubicasa")
class CubiCasaAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load vendors/cubicasa floortrans + weights.")

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("RotateNTurns TTA, split_prediction post-processing.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(
            cubicasa_rooms=ModelRoomOutput(),
            cubicasa_boundaries=ModelBoundaryOutput(),
        )
