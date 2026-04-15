from __future__ import annotations

from pathlib import Path

from backend.pipeline.core.config import load_config


def test_load_config() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root / "config")
    assert cfg.pipeline.mode in ("light", "deep")
    assert "cubicasa" in cfg.models.models
