"""Top-level orchestrator: chain stages, manage mode."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core.config import AppConfig, load_config
from .core.schemas import ImageTensor, PipelineMode
from .stage0_input.loader import load_raster_input
from .stage0_input.normalizer import normalize_image
from .stage1_perception.perception_orchestrator import PerceptionOrchestrator
from .stage2_fusion.fusion_router import FusionRouter


def run_pipeline(
    image_path: str | Path,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run a functional Phase-1 Light pipeline vertical slice:
    loader -> normalizer -> perception -> fusion -> API-shaped output.
    """
    root = Path(__file__).resolve().parents[2]
    cfg_path = Path(config_dir) if config_dir else root / "config"
    config: AppConfig = load_config(cfg_path)
    image_path = Path(image_path)

    mode = PipelineMode(config.pipeline.mode)
    loaded, source_format = load_raster_input(image_path)
    normalized = normalize_image(loaded, target_max_dim=int(config.pipeline.resolution.get("target_max_dim", 1024)))
    stage0 = ImageTensor(data=normalized, original_shape=normalized.shape[:2], scale=1.0)

    perception = PerceptionOrchestrator(mode=mode).run(stage0)
    fused = FusionRouter(mode).fuse(perception)

    diagnostics = dict(perception.diagnostics)
    diagnostics["fusion"] = fused.get("diagnostics", {}) if isinstance(fused, dict) else {}

    payload = {
        "mode": mode.value,  # kept for existing tests
        "pipeline": {
            "mode": mode.value,
            "source_format": source_format,
            "thresholds": config.pipeline.thresholds,
            "resolution": config.pipeline.resolution,
            "failure_policy": "best_effort",
        },
        "rooms": fused.get("rooms", []) if isinstance(fused, dict) else [],
        "boundaries": [
            {"start": {"x": e.start[0], "y": e.start[1]}, "end": {"x": e.end[0], "y": e.end[1]}, "confidence": e.confidence}
            for e in fused.get("boundaries", [])
        ] if isinstance(fused, dict) else [],
        "scale": None,
        "metadata": {
            "input_image": str(image_path),
            "image_width": int(normalized.shape[1]),
            "image_height": int(normalized.shape[0]),
            "diagnostics": diagnostics,
            "perception_dump": asdict(perception),
        },
    }

    return {
        **payload,
    }
