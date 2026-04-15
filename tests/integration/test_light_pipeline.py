"""End-to-end light mode (stub until loaders implemented)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.pipeline import run_pipeline


def test_run_pipeline_loads_config() -> None:
    root = Path(__file__).resolve().parents[2]
    out = run_pipeline(root / "tests" / "fixtures" / "sample_floorplans" / ".gitkeep", config_dir=root / "config")
    assert "mode" in out
    assert out["mode"] in ("light", "deep")
