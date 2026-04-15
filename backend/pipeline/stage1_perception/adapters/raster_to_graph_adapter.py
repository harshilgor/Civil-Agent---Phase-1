"""Raster-to-Graph: Stage 0 RGB, LIFULL-style preprocess, graph → edges."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import ModelLoadError, resolve_module, resolve_weights_path


@registry.register("raster_to_graph")
class RasterToGraphAdapter(BasePerceptionAdapter):
    def __init__(self) -> None:
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None

    def load(self, weights_path: str | None = None) -> None:
        resolved = resolve_module(
            vendor_path="vendors/raster_to_graph",
            local_module_candidates=("models",),
            external_module_candidates=("raster_to_graph",),
        )
        chosen_weights = weights_path or "vendors/raster_to_graph/weights"
        weights = resolve_weights_path(chosen_weights, require_file=False)
        self.model_source = resolved.source
        self.model_module = resolved.module_name
        self.weights_path = weights

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        if self.weights_path is None:
            raise ModelLoadError("Raster-to-Graph model is not loaded.")
        raise NotImplementedError(
            "Phase 1 only guarantees load+weights validation; inference wiring is next."
        )

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        diagnostics: dict[str, Any] = {}
        if isinstance(raw, dict):
            diagnostics = raw
        elif isinstance(raw, Exception):
            diagnostics = {"error": str(raw)}
        if self.weights_path is not None:
            diagnostics.setdefault("raster_to_graph_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("raster_to_graph_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("raster_to_graph_model_source", self.model_source)
        return UnifiedPerceptionOutput(raster_to_graph_edges=[], diagnostics=diagnostics)
