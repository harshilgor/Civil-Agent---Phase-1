"""Generate a 4×5 grid of 20 augmented variants of a floor-plan image.

Usage::

    python scripts/visualize_augmentations.py <input.png> [output.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from src.cv.augmentation import build_training_augmentation


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) >= 3 else inp.with_name(f"{inp.stem}_aug_grid.png")

    img = cv2.imread(str(inp))
    if img is None:
        raise FileNotFoundError(f"Could not read {inp}")

    augmentor = build_training_augmentation(heavy=False)

    cols = 5
    rows = 4
    samples = []
    for _ in range(cols * rows):
        out_d = augmentor(image=img)
        aug = out_d["image"]
        if aug.shape != img.shape:
            aug = cv2.resize(aug, (img.shape[1], img.shape[0]))
        samples.append(aug)

    thumb_w = max(img.shape[1] // cols, 200)
    thumb_h = max(img.shape[0] // cols, int(thumb_w * img.shape[0] / img.shape[1]))
    thumbs = [cv2.resize(s, (thumb_w, thumb_h)) for s in samples]

    row_imgs = [
        np.hstack(thumbs[r * cols: (r + 1) * cols]) for r in range(rows)
    ]
    grid = np.vstack(row_imgs)
    cv2.imwrite(str(out), grid)
    print(f"Wrote augmentation grid → {out}")


if __name__ == "__main__":
    main()
