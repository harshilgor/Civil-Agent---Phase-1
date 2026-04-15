"""Run exactly one perception model: load image → infer → save PNG artifacts locally."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from backend.pipeline.core.registry import registry
from backend.pipeline.stage1_perception.density_map_synthesizer import synthesize_density_map

# Models exercised by sample_model_tester / per-branch demos.
KNOWN_SINGLE_MODELS = [
    "cubicasa",
    "deepfloorplan",
    "roomformer",
    "polyroom",
    "raster_to_graph",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_active_model_name(config_dir: str | Path | None = None) -> str:
    """Branch-specific model id: env CIVIL_ACTIVE_MODEL, else config/active_model.txt."""
    import os

    env = os.environ.get("CIVIL_ACTIVE_MODEL", "").strip()
    if env:
        return env
    cfg = Path(config_dir) if config_dir else PROJECT_ROOT / "config"
    path = cfg / "active_model.txt"
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path} (or set CIVIL_ACTIVE_MODEL)")
    name = path.read_text(encoding="utf-8").strip()
    if not name:
        raise ValueError(f"{path} is empty")
    return name


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
        "saved_rooms": str(room_path.name),
        "saved_walls": str(wall_path.name),
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
        "saved_rooms": str(room_path.name),
        "saved_boundaries": str(boundary_path.name),
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
        "saved_density_map": str(density_path.name),
        "saved_polygons_overlay": str(result_path.name),
        "polygon_count": int(raw.get("polygon_count", 0)),
        "pred_logits_shape": list(np.asarray(raw["pred_logits"]).shape),
        "pred_coords_shape": list(np.asarray(raw["pred_coords"]).shape),
    }


def run_single_model(
    image_path: Path,
    output_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    """Load one adapter, predict, write PNGs under output_dir. No fusion, no other models."""
    from backend.pipeline.stage1_perception import adapters  # noqa: F401

    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "model": model_name,
        "loaded": False,
        "predicted": False,
        "errors": [],
        "traceback": None,
        "artifacts": {},
        "artifact_files": [],
    }

    if model_name not in registry.names():
        msg = f"Unknown model '{model_name}'. Registry has: {registry.names()}"
        result["errors"].append(msg)
        (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    image_rgb = _prepare_rgb(image_path)
    adapter = registry.get(model_name)()

    try:
        adapter.load()
        result["loaded"] = True
    except Exception as exc:
        result["errors"].append(f"load failed: {exc}")
        result["traceback"] = traceback.format_exc()
        (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    try:
        if model_name in ("roomformer", "polyroom"):
            density = synthesize_density_map(image_rgb[..., 0], size=(256, 256))
            raw = adapter.predict(density)
        else:
            raw = adapter.predict(image_rgb)
        result["predicted"] = True
        if model_name == "cubicasa":
            result["artifacts"] = _save_cubicasa_outputs(raw, output_dir)
        elif model_name == "deepfloorplan":
            result["artifacts"] = _save_deepfloorplan_outputs(raw, output_dir)
        elif model_name == "roomformer":
            result["artifacts"] = _save_roomformer_outputs(raw, image_rgb, output_dir)
        else:
            result["artifacts"] = {"note": "No PNG artifact for this adapter (inference may be stubbed)."}
            if isinstance(raw, dict):
                result["raw_keys"] = list(raw.keys())
    except Exception as exc:
        result["errors"].append(f"predict failed: {exc}")
        result["traceback"] = traceback.format_exc()

    for key, val in list(result.get("artifacts", {}).items()):
        if isinstance(val, str) and val.endswith(".png"):
            result["artifact_files"].append(val)

    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def run_single_model_for_active_branch(
    image_path: Path,
    run_id: str,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve active model from config/env, write under data/single_model_outputs/{run_id}."""
    model_name = get_active_model_name(config_dir)
    base = PROJECT_ROOT / "data" / "single_model_outputs" / run_id
    payload = run_single_model(image_path, base, model_name)
    payload["run_id"] = run_id
    payload["output_dir"] = str(base.relative_to(PROJECT_ROOT))
    return payload
