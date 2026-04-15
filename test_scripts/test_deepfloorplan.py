#!/usr/bin/env python3
"""DeepFloorplan inference test: load weights + run sample image."""

from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VENDOR = ROOT / "vendors" / "tf2_deepfloorplan"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from dfp.data import convert_one_hot_to_image  # noqa: E402
from dfp.deploy import predict  # noqa: E402
from dfp.net import deepfloorplanModel  # noqa: E402
from dfp.utils.rgb_ind_convertor import floorplan_fuse_map, ind2rgb  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepFloorplan inference on one image.")
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / "test_scripts" / "samples" / "simple.png",
    )
    parser.add_argument(
        "--weight",
        type=Path,
        default=ROOT / "vendors" / "tf2_deepfloorplan" / "weights" / "log" / "store" / "G",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = ROOT / "test_scripts" / "outputs" / "deepfloorplan"
    output_dir.mkdir(parents=True, exist_ok=True)

    import tensorflow as tf  # noqa: E402

    cfg = SimpleNamespace(
        feature_channels=[256, 128, 64, 32],
        backbone="vgg16",
        feature_names=[
            "block1_pool",
            "block2_pool",
            "block3_pool",
            "block4_pool",
            "block5_pool",
        ],
    )
    model = deepfloorplanModel(config=cfg)

    raw = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
    shp = raw.shape
    img = tf.convert_to_tensor(raw, dtype=tf.uint8)
    img = tf.image.resize(img, [512, 512])
    img = tf.cast(img, dtype=tf.float32) / 255.0
    img = tf.reshape(img, [-1, 512, 512, 3])

    _ = model(tf.zeros((1, 512, 512, 3), dtype=tf.float32))
    ckpt = tf.train.Checkpoint(model=model)
    ckpt.restore(str(args.weight)).expect_partial()

    logits_cw, logits_r = predict(model, img, shp)

    logits_r = tf.image.resize(logits_r, shp[:2])
    logits_cw = tf.image.resize(logits_cw, shp[:2])

    room_idx = convert_one_hot_to_image(logits_r)[0].numpy().squeeze().astype(np.uint8)
    boundary_idx = convert_one_hot_to_image(logits_cw)[0].numpy().squeeze().astype(np.uint8)

    room_rgb = ind2rgb(room_idx, color_map=floorplan_fuse_map).astype(np.uint8)
    boundary_bin = np.where(boundary_idx > 0, 255, 0).astype(np.uint8)

    room_path = output_dir / "rooms.png"
    boundary_path = output_dir / "boundaries.png"
    Image.fromarray(room_rgb, mode="RGB").save(room_path)
    Image.fromarray(boundary_bin, mode="L").save(boundary_path)

    room_classes = np.unique(room_idx)
    boundary_classes = np.unique(boundary_idx)
    print("deepfloorplan: PASS")
    print(f"input={args.image} original_size={tuple(int(v) for v in shp[:2])}")
    print(f"logits_room_shape={tuple(int(v) for v in logits_r.shape)} logits_boundary_shape={tuple(int(v) for v in logits_cw.shape)}")
    print(f"detected_room_classes={room_classes.tolist()} boundary_classes={boundary_classes.tolist()}")
    print(f"saved_rooms={room_path}")
    print(f"saved_boundaries={boundary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
