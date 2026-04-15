#!/usr/bin/env python3
"""CubiCasa inference test: load weights + run sample image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VENDOR = ROOT / "vendors" / "cubicasa"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from floortrans.models.hg_furukawa_original import hg_furukawa_original  # noqa: E402
from floortrans.post_prosessing import split_prediction  # noqa: E402


def _palette(num_classes: int = 12) -> np.ndarray:
    # Fixed palette for deterministic room-mask visualization.
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CubiCasa inference on one image.")
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / "test_scripts" / "samples" / "simple.png",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "vendors" / "cubicasa" / "weights" / "model_best_val_loss_var.pkl",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = ROOT / "test_scripts" / "outputs" / "cubicasa"
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(args.image).convert("RGB")
    orig_w, orig_h = image.size
    target_h = 512
    target_w = max(64, int(round(orig_w * (target_h / max(orig_h, 1)) / 32.0) * 32))
    image_resized = image.resize((target_w, target_h), Image.Resampling.BILINEAR)

    arr = np.asarray(image_resized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
    tensor = tensor * 2.0 - 1.0

    model = hg_furukawa_original(n_classes=51)
    model.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
    checkpoint = torch.load(str(args.weights), map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    with torch.no_grad():
        pred = model(tensor)
    heatmaps, rooms, _icons = split_prediction(pred.cpu(), (target_h, target_w), [21, 12, 11])

    room_mask = np.argmax(rooms, axis=0).astype(np.uint8)
    # Boundary approximation for phase-1 visual check.
    wall_score = np.max(heatmaps[:13], axis=0)
    walls = (wall_score > 0.03).astype(np.uint8) * 255

    room_img = Image.fromarray(_palette(12)[room_mask], mode="RGB").resize(
        (orig_w, orig_h), Image.Resampling.NEAREST
    )
    wall_img = Image.fromarray(walls, mode="L").resize(
        (orig_w, orig_h), Image.Resampling.NEAREST
    )

    room_path = output_dir / "rooms.png"
    wall_path = output_dir / "walls.png"
    room_img.save(room_path)
    wall_img.save(wall_path)

    classes = np.unique(room_mask)
    print(f"cubicasa: PASS")
    print(f"input={args.image} original_size=({orig_h},{orig_w}) model_size=({target_h},{target_w})")
    print(f"output_tensor_shape={tuple(pred.shape)} room_probs_shape={rooms.shape} heatmaps_shape={heatmaps.shape}")
    print(f"detected_room_classes={classes.tolist()} count={len(classes)}")
    print(f"saved_rooms={room_path}")
    print(f"saved_walls={wall_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
