"""Load and validate YAML configs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PipelineConfig(BaseModel):
    mode: str = "light"
    resolution: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)


class ModelsRootConfig(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, Any] = Field(default_factory=dict)


class ScaleConfig(BaseModel):
    ocr: dict[str, Any] = Field(default_factory=dict)
    scale_bar: dict[str, Any] = Field(default_factory=dict)
    resolver: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    pipeline: PipelineConfig
    models: ModelsRootConfig
    scale: ScaleConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_config(config_dir: str | Path) -> AppConfig:
    """Load config/*.yaml from a directory and validate."""
    root = Path(config_dir)
    pipeline = PipelineConfig.model_validate(_read_yaml(root / "pipeline.yaml"))
    models = ModelsRootConfig.model_validate(_read_yaml(root / "models.yaml"))
    scale = ScaleConfig.model_validate(_read_yaml(root / "scale.yaml"))
    return AppConfig(pipeline=pipeline, models=models, scale=scale)
