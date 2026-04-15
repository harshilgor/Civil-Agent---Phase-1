"""Phase 1 parallel models; Phase 2 density → RoomFormer/PolyRoom (deep mode)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.schemas import ImageTensor, PipelineMode, UnifiedPerceptionOutput
from .density_map_synthesizer import synthesize_density_map


class PerceptionOrchestrator:
    """
    Phase 1 (parallel): CubiCasa + DeepFloorplan + Raster-to-Graph (+ optional FloorplanTransform).
    Phase 2 (sequential, deep): density map synthesis → RoomFormer or PolyRoom.
    Manages TF vs PyTorch isolation (subprocess / separate processes).
    """

    def __init__(self, mode: PipelineMode = PipelineMode.LIGHT) -> None:
        self.mode = mode

    @staticmethod
    def _merge_output(dst: UnifiedPerceptionOutput, src: UnifiedPerceptionOutput) -> None:
        if src.cubicasa_rooms is not None:
            dst.cubicasa_rooms = src.cubicasa_rooms
        if src.cubicasa_boundaries is not None:
            dst.cubicasa_boundaries = src.cubicasa_boundaries
        if src.deepfloorplan_rooms is not None:
            dst.deepfloorplan_rooms = src.deepfloorplan_rooms
        if src.deepfloorplan_boundaries is not None:
            dst.deepfloorplan_boundaries = src.deepfloorplan_boundaries
        if src.raster_to_graph_edges:
            dst.raster_to_graph_edges = src.raster_to_graph_edges
        if src.floorplan_transform_edges:
            dst.floorplan_transform_edges = src.floorplan_transform_edges
        if src.roomformer_polygons:
            dst.roomformer_polygons = src.roomformer_polygons
        if src.polyroom_polygons:
            dst.polyroom_polygons = src.polyroom_polygons
        if src.diagnostics:
            dst.diagnostics.update(src.diagnostics)

    def run(self, stage0_rgb: ImageTensor) -> UnifiedPerceptionOutput:
        # Import adapters to ensure registry is populated
        from . import adapters  # noqa: F401
        from ..core.registry import registry

        result = UnifiedPerceptionOutput()
        diagnostics: dict[str, Any] = {"mode": self.mode.value}

        if self.mode == PipelineMode.LIGHT:
            phase1_models = ["cubicasa", "deepfloorplan"]
        else:
            phase1_models = ["cubicasa", "deepfloorplan", "raster_to_graph"]

        for model_name in phase1_models:
            status: dict[str, Any] = {"loaded": False}
            try:
                adapter = registry.get(model_name)()
                adapter.load()
                status["loaded"] = True
                try:
                    raw = adapter.predict(stage0_rgb.data)
                    status["predicted"] = True
                    unified = adapter.to_unified_output(raw)
                    self._merge_output(result, unified)
                except Exception as exc:  # pragma: no cover - defensive diagnostics path
                    status["predicted"] = False
                    status["predict_error"] = str(exc)
            except Exception as exc:  # pragma: no cover - defensive diagnostics path
                status["error"] = str(exc)
            diagnostics[model_name] = status

        if self.mode == PipelineMode.DEEP:
            try:
                sample: Any | None = None
                if result.cubicasa_boundaries is not None and result.cubicasa_boundaries.wall_mask is not None:
                    sample = np.asarray(result.cubicasa_boundaries.wall_mask)
                elif (
                    result.deepfloorplan_boundaries is not None
                    and result.deepfloorplan_boundaries.wall_mask is not None
                ):
                    sample = np.asarray(result.deepfloorplan_boundaries.wall_mask)
                elif stage0_rgb.data is not None:
                    sample = np.asarray(stage0_rgb.data)
                    if sample.ndim == 3:
                        sample = sample[..., 0]
                if sample is not None:
                    density = synthesize_density_map(sample, size=(256, 256))
                    diagnostics["density_map"] = {"shape": tuple(int(v) for v in density.shape)}
                    roomformer_status: dict[str, Any] = {"loaded": False}
                    try:
                        roomformer = registry.get("roomformer")()
                        roomformer.load()
                        roomformer_status["loaded"] = True
                        raw = roomformer.predict(density)
                        roomformer_status["predicted"] = True
                        self._merge_output(result, roomformer.to_unified_output(raw))
                    except Exception as exc:  # pragma: no cover
                        roomformer_status["error"] = str(exc)
                    diagnostics["roomformer"] = roomformer_status
            except Exception as exc:  # pragma: no cover - diagnostics only
                diagnostics["density_map"] = {"error": str(exc)}

        diagnostics["failure_policy"] = "best_effort"
        diagnostics["overall_status"] = "complete_with_warnings" if any(
            (not diagnostics.get(name, {}).get("loaded", False))
            or (not diagnostics.get(name, {}).get("predicted", False))
            for name in phase1_models
        ) else "complete"
        result.diagnostics = diagnostics
        return result
