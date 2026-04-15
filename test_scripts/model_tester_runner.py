#!/usr/bin/env python3
"""Run one sample image through each stage-1 model adapter and save outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.core.registry import registry  # noqa: E402
from backend.pipeline.stage1_perception import adapters  # noqa: F401, E402
from backend.pipeline.single_model_run import (  # noqa: E402
    KNOWN_SINGLE_MODELS,
    run_single_model,
)

MODEL_ORDER = list(KNOWN_SINGLE_MODELS)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _run_one_model(model_name: str, image_path: Path, output_root: Path) -> dict[str, Any]:
    model_dir = output_root / model_name
    model_dir.mkdir(parents=True, exist_ok=True)
    if model_name not in registry.names():
        result = {"model": model_name, "loaded": False, "predicted": False, "error": "unknown adapter"}
        _save_json(model_dir / "result.json", result)
        return result
    result = run_single_model(image_path, model_dir, model_name)
    if result.get("errors"):
        result["error"] = "; ".join(result["errors"])
    return result


def run_models(image_path: Path, models: list[str]) -> int:
    if not image_path.exists():
        print(f"ERROR: input image not found: {image_path}")
        return 1

    output_root = ROOT / "test_scripts" / "outputs" / "sample_model_tester"
    output_root.mkdir(parents=True, exist_ok=True)

    run_summary: list[dict[str, Any]] = []
    for model_name in models:
        run_summary.append(_run_one_model(model_name, image_path, output_root))

    summary_payload = {
        "input_image": str(image_path),
        "outputs_root": str(output_root),
        "results": run_summary,
    }
    _save_json(output_root / "summary.json", summary_payload)

    print("sample_model_tester: complete")
    print(f"input_image={image_path}")
    print(f"outputs_root={output_root}")
    for row in run_summary:
        status = "PASS" if row.get("loaded") and row.get("predicted") else "WARN"
        print(
            f"{row['model']}: {status} loaded={row.get('loaded')} predicted={row.get('predicted')}"
        )
        if row.get("error"):
            print(f"  error={row['error']}")
    print(f"saved_summary={output_root / 'summary.json'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run sample_model_tester_img.png through each model and save outputs."
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / "sample_model_tester_img.png",
        help="Sample image path. Default expects sample_model_tester_img.png in repo root.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODEL_ORDER,
        help=f"Models to run. Default: {' '.join(MODEL_ORDER)}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_models(args.image, args.models)


if __name__ == "__main__":
    raise SystemExit(main())
