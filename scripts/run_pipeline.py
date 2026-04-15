#!/usr/bin/env python3
"""CLI entry point for the civil-agent pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Run civil-agent floor plan pipeline")
    p.add_argument("image", type=Path, help="Input floor plan image (PNG/JPG/PDF)")
    p.add_argument("--config", type=Path, default=ROOT / "config", help="Config directory")
    args = p.parse_args()
    result = run_pipeline(args.image, config_dir=args.config)
    print(result)


if __name__ == "__main__":
    main()
