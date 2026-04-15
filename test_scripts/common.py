"""Shared helpers for phase-1 adapter smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.core.registry import registry  # noqa: E402
from backend.pipeline.stage1_perception import adapters  # noqa: F401, E402


def parse_args(model_name: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Phase-1 load test for {model_name} adapter."
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Override weights path (file or directory depending on adapter).",
    )
    return parser.parse_args()


def run_load_smoke(model_name: str, weights_path: str | None = None) -> int:
    adapter = registry.get(model_name)()
    try:
        adapter.load(weights_path=weights_path)
        output = adapter.to_unified_output(
            {"status": "PASS", "message": f"{model_name} loaded successfully."}
        )
        print(json.dumps(output.diagnostics, indent=2))
        print(f"{model_name}: PASS")
        return 0
    except Exception as exc:
        output = adapter.to_unified_output(exc)
        print(json.dumps(output.diagnostics, indent=2))
        print(f"{model_name}: FAIL ({exc})")
        return 1
