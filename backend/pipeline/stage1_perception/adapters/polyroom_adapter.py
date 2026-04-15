"""PolyRoom: Mask2Former on density map, then polygon refinement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import ModelLoadError, resolve_source_without_import, resolve_weights_path


@registry.register("polyroom")
class PolyRoomAdapter(BasePerceptionAdapter):
    def __init__(self) -> None:
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None

    def load(self, weights_path: str | None = None) -> None:
        source = resolve_source_without_import("vendors/polyroom/models")
        chosen_weights = weights_path or "vendors/polyroom/checkpoints"
        weights = resolve_weights_path(chosen_weights, require_file=False)
        self.model_source = source
        self.model_module = "polyroom.models"
        self.weights_path = weights

    def predict(self, density_map: Any, *args: Any, **kwargs: Any) -> Any:
        if self.weights_path is None:
            raise ModelLoadError("PolyRoom model is not loaded.")
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
            diagnostics.setdefault("polyroom_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("polyroom_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("polyroom_model_source", self.model_source)
        return UnifiedPerceptionOutput(polyroom_polygons=[], diagnostics=diagnostics)
