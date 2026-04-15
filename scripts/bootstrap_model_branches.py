#!/usr/bin/env python3
"""Create model/<name> branches: one adapter, single-model pipeline + orchestrator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODELS = ["cubicasa", "deepfloorplan", "roomformer", "polyroom", "raster_to_graph"]

PIPELINE_SINGLE = '''"""Top-level orchestrator: single active model only (branch-specific)."""

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
'''

ORCHESTRATOR_SINGLE = '''"""Single active model on this branch (no parallel models)."""

from __future__ import annotations

from typing import Any

from ..core.registry import registry
from ..core.schemas import ImageTensor, PipelineMode, UnifiedPerceptionOutput
from ..single_model_run import get_active_model_name
from .density_map_synthesizer import synthesize_density_map


class PerceptionOrchestrator:
    def __init__(self, mode: PipelineMode = PipelineMode.LIGHT) -> None:
        self.mode = mode

    def run(self, stage0_rgb: ImageTensor) -> UnifiedPerceptionOutput:
        from . import adapters  # noqa: F401

        model_name = get_active_model_name()
        diagnostics: dict[str, Any] = {"mode": self.mode.value, "active_model": model_name}
        result = UnifiedPerceptionOutput()
        try:
            adapter = registry.get(model_name)()
            adapter.load()
            if model_name in ("roomformer", "polyroom"):
                density = synthesize_density_map(stage0_rgb.data[..., 0], size=(256, 256))
                raw = adapter.predict(density)
            else:
                raw = adapter.predict(stage0_rgb.data)
            unified = adapter.to_unified_output(raw)
            diagnostics["loaded"] = True
            diagnostics["predicted"] = True
            unified.diagnostics.update(diagnostics)
            return unified
        except Exception as exc:  # noqa: BLE001
            diagnostics["error"] = str(exc)
            result.diagnostics = diagnostics
            return result
'''


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def adapter_init_py(model: str) -> str:
    mod = f"{model}_adapter"
    return f'''"""Import adapters to register with the global registry (single model: {model})."""

from . import {mod}

__all__ = ["{mod}"]
'''


def main() -> int:
    for model in MODELS:
        _run(["git", "checkout", "main"])
        _run(["git", "checkout", "-b", f"model/{model}"])
        (ROOT / "config" / "active_model.txt").write_text(f"{model}\n", encoding="utf-8")
        (ROOT / "backend" / "pipeline" / "pipeline.py").write_text(PIPELINE_SINGLE, encoding="utf-8")
        (ROOT / "backend" / "pipeline" / "stage1_perception" / "perception_orchestrator.py").write_text(
            ORCHESTRATOR_SINGLE, encoding="utf-8"
        )
        (ROOT / "backend" / "pipeline" / "stage1_perception" / "adapters" / "__init__.py").write_text(
            adapter_init_py(model), encoding="utf-8"
        )
        _run(["git", "add", "config/active_model.txt", "backend/pipeline/pipeline.py"])
        _run(["git", "add", "backend/pipeline/stage1_perception/perception_orchestrator.py"])
        _run(["git", "add", "backend/pipeline/stage1_perception/adapters/__init__.py"])
        _run(["git", "commit", "-m", f"Branch model/{model}: single adapter and pipeline"])
    _run(["git", "checkout", "main"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
