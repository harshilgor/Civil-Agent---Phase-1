"""Single active model on this branch (no parallel models)."""

from __future__ import annotations

from typing import Any

from ..core.registry import registry
from ..core.schemas import ImageTensor, PipelineMode, UnifiedPerceptionOutput
from ..single_model_run import get_active_model_name
from .density_map_synthesizer import synthesize_density_map


class PerceptionOrchestrator:
    def __init__(self, mode: PipelineMode = PipelineMode.LIGHT) -> None:
        self.mode = mode

    def run(self, stage0_rgb: ImageTensor) -> UnifiedPerceptionOutput:
        from . import adapters  # noqa: F401

        model_name = get_active_model_name()
        diagnostics: dict[str, Any] = {"mode": self.mode.value, "active_model": model_name}
        result = UnifiedPerceptionOutput()
        try:
            adapter = registry.get(model_name)()
            adapter.load()
            if model_name in ("roomformer", "polyroom"):
                density = synthesize_density_map(stage0_rgb.data[..., 0], size=(256, 256))
                raw = adapter.predict(density)
            else:
                raw = adapter.predict(stage0_rgb.data)
            unified = adapter.to_unified_output(raw)
            diagnostics["loaded"] = True
            diagnostics["predicted"] = True
            unified.diagnostics.update(diagnostics)
            return unified
        except Exception as exc:  # noqa: BLE001
            diagnostics["error"] = str(exc)
            result.diagnostics = diagnostics
            return result
