"""Top-level orchestrator: chain stages, manage mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core.config import AppConfig, load_config


def run_pipeline(
    image_path: str | Path,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Load config and return pipeline metadata. Full stage chain is wired in
    stage modules (currently stubs).
    """
    root = Path(__file__).resolve().parents[2]
    cfg_path = Path(config_dir) if config_dir else root / "config"
    _config: AppConfig = load_config(cfg_path)
    return {
        "image": str(Path(image_path)),
        "mode": _config.pipeline.mode,
        "thresholds": _config.pipeline.thresholds,
    }
