#!/usr/bin/env python3
"""RoomFormer inference test: load checkpoint + run one density map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ROOMFORMER_VENDOR = ROOT / "vendors" / "roomformer"
if str(ROOMFORMER_VENDOR) not in sys.path:
    sys.path.insert(0, str(ROOMFORMER_VENDOR))

from models import build_model  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RoomFormer inference on one density map.")
    parser.add_argument(
        "--density",
        type=Path,
        default=ROOT / "data" / "stru3d" / "test" / "03250.png",
        help="Input density map PNG from Structured3D processed dataset.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "vendors" / "roomformer" / "checkpoints" / "roomformer_stru3d.pth",
        help="Path to roomformer_stru3d checkpoint.",
    )
    return parser.parse_args()


def _build_args() -> SimpleNamespace:
    return SimpleNamespace(
        backbone="resnet50",
        lr_backbone=0.0,
        dilation=False,
        position_embedding="sine",
        position_embedding_scale=2 * np.pi,
        num_feature_levels=4,
        enc_layers=6,
        dec_layers=6,
        dim_feedforward=1024,
        hidden_dim=256,
        dropout=0.1,
        nheads=8,
        num_queries=800,
        num_polys=20,
        dec_n_points=4,
        enc_n_points=4,
        query_pos_type="sine",
        with_poly_refine=True,
        masked_attn=False,
        semantic_classes=-1,
        aux_loss=True,
        device="cpu",
        set_cost_class=2,
        set_cost_coords=5,
        cls_loss_coef=2,
        room_cls_loss_coef=0.2,
        coords_loss_coef=5,
        raster_loss_coef=1,
    )


def _extract_polygons(
    pred_logits: torch.Tensor, pred_coords: torch.Tensor
) -> list[list[list[int]]]:
    fg_mask = torch.sigmoid(pred_logits) > 0.5
    room_polys: list[list[list[int]]] = []
    for room_idx in range(fg_mask.shape[0]):
        valid = pred_coords[room_idx][fg_mask[room_idx]]
        if valid.numel() == 0:
            continue
        corners = torch.round(valid * 255.0).int().cpu().numpy()
        if len(corners) < 4:
            continue
        try:
            if Polygon(corners).area < 100:
                continue
        except Exception:
            continue
        room_polys.append(corners.tolist())
    return room_polys


def main() -> int:
    args = parse_args()

    output_dir = ROOT / "test_scripts" / "outputs" / "roomformer"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.png"

    density = Image.open(args.density).convert("L")
    density_np = np.asarray(density, dtype=np.float32) / 255.0
    sample = torch.from_numpy(density_np).unsqueeze(0)  # [1, H, W]

    model = build_model(_build_args(), train=False)
    checkpoint = torch.load(str(args.checkpoint), map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"], strict=False)
    model.eval()

    with torch.no_grad():
        outputs = model([sample])

    pred_logits = outputs["pred_logits"][0]
    pred_coords = outputs["pred_coords"][0]
    polygons = _extract_polygons(pred_logits, pred_coords)

    vis = density.convert("RGB")
    draw = ImageDraw.Draw(vis)
    for poly in polygons:
        pts = [(int(x), int(y)) for x, y in poly]
        draw.line(pts + [pts[0]], fill=(255, 64, 64), width=2)
    vis.save(result_path)

    print("roomformer: PASS")
    print(f"density={args.density}")
    print(f"checkpoint={args.checkpoint}")
    print(f"pred_logits_shape={tuple(pred_logits.shape)} pred_coords_shape={tuple(pred_coords.shape)}")
    print(f"polygon_count={len(polygons)}")
    print("polygons_preview=" + json.dumps(polygons[:5]))
    print(f"saved_result={result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
