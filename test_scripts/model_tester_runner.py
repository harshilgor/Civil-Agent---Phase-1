#!/usr/bin/env python3
"""Run one sample image through each stage-1 model adapter and save outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.core.registry import registry  # noqa: E402
from backend.pipeline.stage1_perception import adapters  # noqa: F401, E402
from backend.pipeline.stage1_perception.density_map_synthesizer import (  # noqa: E402
    synthesize_density_map,
)

MODEL_ORDER = [
    "cubicasa",
    "deepfloorplan",
    "roomformer",
    "polyroom",
    "raster_to_graph",
]


def _palette(num_classes: int = 12) -> np.ndarray:
    base = np.array(
        [
            [0, 0, 0],
            [166, 206, 227],
            [31, 120, 180],
            [178, 223, 138],
            [51, 160, 44],
            [251, 154, 153],
            [227, 26, 28],
            [253, 191, 111],
            [255, 127, 0],
            [202, 178, 214],
            [106, 61, 154],
            [255, 255, 153],
        ],
        dtype=np.uint8,
    )
    if num_classes <= base.shape[0]:
        return base[:num_classes]
    extra = np.tile(base[-1], (num_classes - base.shape[0], 1))
    return np.vstack([base, extra])


def _prepare_rgb(image_path: Path) -> np.ndarray:
    return np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _save_cubicasa_outputs(raw: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    room_mask = np.asarray(raw["room_mask"], dtype=np.uint8)
    wall_mask = np.asarray(raw["wall_mask"], dtype=np.uint8) * 255
    input_h, input_w = (int(v) for v in raw["input_size"])

    room_img = Image.fromarray(_palette(12)[room_mask], mode="RGB").resize(
        (input_w, input_h), Image.Resampling.NEAREST
    )
    wall_img = Image.fromarray(wall_mask, mode="L").resize(
        (input_w, input_h), Image.Resampling.NEAREST
    )
    room_path = out_dir / "rooms.png"
    wall_path = out_dir / "walls.png"
    room_img.save(room_path)
    wall_img.save(wall_path)

    classes = np.unique(room_mask)
    return {
        "saved_rooms": str(room_path),
        "saved_walls": str(wall_path),
        "detected_room_classes": classes.tolist(),
        "room_logits_shape": list(np.asarray(raw["room_logits"]).shape),
        "boundary_logits_shape": list(np.asarray(raw["boundary_logits"]).shape),
    }


def _save_deepfloorplan_outputs(raw: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    room_mask = np.asarray(raw["room_mask"], dtype=np.uint8)
    boundary_mask = np.asarray(raw["boundary_mask"], dtype=np.uint8) * 255

    room_img = Image.fromarray(_palette(12)[room_mask], mode="RGB")
    boundary_img = Image.fromarray(boundary_mask, mode="L")
    room_path = out_dir / "rooms.png"
    boundary_path = out_dir / "boundaries.png"
    room_img.save(room_path)
    boundary_img.save(boundary_path)

    return {
        "saved_rooms": str(room_path),
        "saved_boundaries": str(boundary_path),
        "detected_room_classes": np.unique(room_mask).tolist(),
        "room_logits_shape": list(np.asarray(raw["room_logits"]).shape),
        "boundary_logits_shape": list(np.asarray(raw["boundary_logits"]).shape),
    }


def _save_roomformer_outputs(raw: dict[str, Any], image_rgb: np.ndarray, out_dir: Path) -> dict[str, Any]:
    density = synthesize_density_map(image_rgb[..., 0], size=(256, 256))
    density_img = Image.fromarray(np.clip(density * 255.0, 0, 255).astype(np.uint8), mode="L")
    density_path = out_dir / "density_map.png"
    density_img.save(density_path)

    h, w = image_rgb.shape[:2]
    sx = w / 255.0
    sy = h / 255.0
    vis = Image.fromarray(image_rgb.copy(), mode="RGB")
    draw = ImageDraw.Draw(vis)
    for poly in raw.get("polygons", []):
        pts = [(int(round(p[0] * sx)), int(round(p[1] * sy))) for p in poly]
        if len(pts) >= 2:
            draw.line(pts + [pts[0]], fill=(255, 64, 64), width=2)

    result_path = out_dir / "polygons_overlay.png"
    vis.save(result_path)
    return {
        "saved_density_map": str(density_path),
        "saved_polygons_overlay": str(result_path),
        "polygon_count": int(raw.get("polygon_count", 0)),
        "pred_logits_shape": list(np.asarray(raw["pred_logits"]).shape),
        "pred_coords_shape": list(np.asarray(raw["pred_coords"]).shape),
    }


def _run_one_model(model_name: str, image_rgb: np.ndarray, output_root: Path) -> dict[str, Any]:
    model_dir = output_root / model_name
    model_dir.mkdir(parents=True, exist_ok=True)
    adapter = registry.get(model_name)()

    result: dict[str, Any] = {"model": model_name, "loaded": False, "predicted": False}
    try:
        adapter.load()
        result["loaded"] = True
    except Exception as exc:
        result["error"] = f"load failed: {exc}"
        _save_json(model_dir / "result.json", result)
        return result

    try:
        if model_name == "roomformer":
            density = synthesize_density_map(image_rgb[..., 0], size=(256, 256))
            raw = adapter.predict(density)
        else:
            raw = adapter.predict(image_rgb)
        result["predicted"] = True
        if model_name == "cubicasa":
            result["artifacts"] = _save_cubicasa_outputs(raw, model_dir)
        elif model_name == "deepfloorplan":
            result["artifacts"] = _save_deepfloorplan_outputs(raw, model_dir)
        elif model_name == "roomformer":
            result["artifacts"] = _save_roomformer_outputs(raw, image_rgb, model_dir)
        else:
            # Raster-to-Graph and PolyRoom currently don't expose inference wiring in phase 1.
            result["artifacts"] = {"note": "No visual artifact generated by this adapter yet."}
            if isinstance(raw, dict):
                result["raw"] = raw
    except Exception as exc:
        result["error"] = f"predict failed: {exc}"
        try:
            unified = adapter.to_unified_output(exc)
            result["diagnostics"] = unified.diagnostics
        except Exception:
            pass

    _save_json(model_dir / "result.json", result)
    return result


def run_models(image_path: Path, models: list[str]) -> int:
    if not image_path.exists():
        print(f"ERROR: input image not found: {image_path}")
        return 1

    output_root = ROOT / "test_scripts" / "outputs" / "sample_model_tester"
    output_root.mkdir(parents=True, exist_ok=True)
    image_rgb = _prepare_rgb(image_path)

    run_summary: list[dict[str, Any]] = []
    for model_name in models:
        if model_name not in registry.names():
            run_summary.append(
                {"model": model_name, "loaded": False, "predicted": False, "error": "unknown adapter"}
            )
            continue
        run_summary.append(_run_one_model(model_name, image_rgb, output_root))

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
