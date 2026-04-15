"""Phase 1 parallel models; Phase 2 density → RoomFormer/PolyRoom (deep mode)."""

from __future__ import annotations

from typing import Any

from ..core.schemas import ImageTensor, PipelineMode, UnifiedPerceptionOutput


class PerceptionOrchestrator:
    """
    Phase 1 (parallel): CubiCasa + DeepFloorplan + Raster-to-Graph (+ optional FloorplanTransform).
    Phase 2 (sequential, deep): density map synthesis → RoomFormer or PolyRoom.
    Manages TF vs PyTorch isolation (subprocess / separate processes).
    """

    def __init__(self, mode: PipelineMode = PipelineMode.LIGHT) -> None:
        self.mode = mode

    def run(self, stage0_rgb: ImageTensor) -> UnifiedPerceptionOutput:
        # Import adapters to ensure registry is populated
        from . import adapters  # noqa: F401

        raise NotImplementedError(
            "Wire parallel phase, fusion hooks, and optional deep phase; isolate TF."
        )
