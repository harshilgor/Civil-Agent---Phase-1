#!/usr/bin/env python3
"""Run Stage-1 perception orchestrator end-to-end on one sample image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.core.schemas import ImageTensor, PipelineMode
from backend.pipeline.stage1_perception.perception_orchestrator import PerceptionOrchestrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-to-end perception orchestrator.")
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / "test_scripts" / "samples" / "simple.png",
        help="Input image path.",
    )
    parser.add_argument(
        "--mode",
        choices=["light", "deep"],
        default="deep",
        help="Pipeline mode to run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    img = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
    stage0 = ImageTensor(data=img.astype(np.float32) / 255.0, original_shape=img.shape[:2], scale=1.0)
    orchestrator = PerceptionOrchestrator(mode=PipelineMode(args.mode))
    output = orchestrator.run(stage0)

    summary = {
        "mode": args.mode,
        "cubicasa_room_logits_shape": (
            list(output.cubicasa_rooms.room_logits.shape)
            if output.cubicasa_rooms and output.cubicasa_rooms.room_logits is not None
            else None
        ),
        "deepfloorplan_room_logits_shape": (
            list(output.deepfloorplan_rooms.room_logits.shape)
            if output.deepfloorplan_rooms and output.deepfloorplan_rooms.room_logits is not None
            else None
        ),
        "roomformer_polygon_count": len(output.roomformer_polygons),
        "diagnostics": output.diagnostics,
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
