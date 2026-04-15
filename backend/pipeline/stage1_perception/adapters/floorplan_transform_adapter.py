"""FloorplanTransformation: junction detection → IP solver → edges."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("floorplan_transformation")
class FloorplanTransformAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load pytorch floorplan_transformation weights.")

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Junction net + IP solver.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(floorplan_transform_edges=[])
