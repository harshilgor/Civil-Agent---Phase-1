"""Static trust hierarchy weights from config."""

from __future__ import annotations

from typing import Any


def trust_weights(models_config: dict[str, Any]) -> dict[str, float]:
    """Map model name → weight from models.yaml."""
    out: dict[str, float] = {}
    for name, spec in models_config.get("models", {}).items():
        if isinstance(spec, dict) and "trust_weight" in spec:
            out[name] = float(spec["trust_weight"])
    return out
