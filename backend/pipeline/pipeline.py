"""Top-level orchestrator: single active model only (branch-specific)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .core.config import AppConfig, load_config
from .single_model_run import run_single_model_for_active_branch


def run_pipeline(
    image_path: str | Path,
    config_dir: str | Path | None = None,
    mode_override: str | None = None,
) -> dict[str, Any]:
    """Input → active adapter → PNG artifacts under data/single_model_outputs; no fusion."""
    root = Path(__file__).resolve().parents[2]
    cfg_path = Path(config_dir) if config_dir else root / "config"
    config: AppConfig = load_config(cfg_path)
    image_path = Path(image_path)
    run_id = uuid4().hex

    try:
        sm = run_single_model_for_active_branch(image_path, run_id, config_dir=cfg_path)
        return {
            "mode": "light",
            "pipeline": {
                "mode": "light",
                "single_model_branch": True,
                "requested_mode": mode_override or config.pipeline.mode,
                "thresholds": config.pipeline.thresholds,
                "resolution": config.pipeline.resolution,
                "failure_policy": "single_model_only",
            },
            "rooms": [],
            "boundaries": [],
            "scale": None,
            "metadata": {
                "input_image": str(image_path),
                "single_model": sm,
                "diagnostics": {
                    "errors": sm.get("errors", []),
                    "traceback": sm.get("traceback"),
                    "loaded": sm.get("loaded"),
                    "predicted": sm.get("predicted"),
                    "model": sm.get("model"),
                },
            },
        }
    except Exception as exc:
        return {
            "mode": "light",
            "pipeline": {
                "mode": "light",
                "single_model_branch": True,
                "requested_mode": mode_override or config.pipeline.mode,
                "thresholds": config.pipeline.thresholds,
                "resolution": config.pipeline.resolution,
                "failure_policy": "single_model_only",
            },
            "rooms": [],
            "boundaries": [],
            "scale": None,
            "metadata": {
                "input_image": str(image_path),
                "diagnostics": {"pipeline_error": str(exc)},
            },
        }
