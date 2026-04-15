"""FloorplanTransformation: junction detection → IP solver → edges."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import ModelLoadError, resolve_module, resolve_weights_path


@registry.register("floorplan_transformation")
class FloorplanTransformAdapter(BasePerceptionAdapter):
    def __init__(self) -> None:
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None

    def load(self, weights_path: str | None = None) -> None:
        resolved = resolve_module(
            vendor_path="vendors/floorplan_transformation",
            local_module_candidates=("models",),
            external_module_candidates=("floorplan_transformation",),
        )
        chosen_weights = weights_path or "vendors/floorplan_transformation/weights"
        weights = resolve_weights_path(chosen_weights, require_file=False)
        self.model_source = resolved.source
        self.model_module = resolved.module_name
        self.weights_path = weights

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        if self.weights_path is None:
            raise ModelLoadError("FloorplanTransformation model is not loaded.")
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
            diagnostics.setdefault("floorplan_transform_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("floorplan_transform_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("floorplan_transform_model_source", self.model_source)
        return UnifiedPerceptionOutput(floorplan_transform_edges=[], diagnostics=diagnostics)
