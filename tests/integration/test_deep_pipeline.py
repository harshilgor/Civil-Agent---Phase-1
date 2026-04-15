"""End-to-end deep mode (stub)."""

from __future__ import annotations

from pathlib import Path

from backend.pipeline import run_pipeline


def test_deep_config_roundtrip() -> None:
    root = Path(__file__).resolve().parents[2]
    out = run_pipeline("fixture.png", config_dir=root / "config")
    assert out["mode"] == "light"  # default in pipeline.yaml
