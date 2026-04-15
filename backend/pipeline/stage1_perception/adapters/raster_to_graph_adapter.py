"""Raster-to-Graph: Stage 0 RGB, LIFULL-style preprocess, graph → edges."""

from __future__ import annotations

from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter


@registry.register("raster_to_graph")
class RasterToGraphAdapter(BasePerceptionAdapter):
    def load(self, weights_path: str | None = None) -> None:
        raise NotImplementedError("Load vendors/raster_to_graph weights.")

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Autoregressive inference; graph decode.")

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        return UnifiedPerceptionOutput(raster_to_graph_edges=[])
