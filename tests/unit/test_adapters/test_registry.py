"""Adapter registry: names resolve after importing adapters."""

from __future__ import annotations

from backend.pipeline.stage1_perception import adapters  # noqa: F401
from backend.pipeline.core.registry import registry


def test_registry_lists_models() -> None:
    names = registry.names()
    assert "cubicasa" in names
    assert "deepfloorplan" in names
