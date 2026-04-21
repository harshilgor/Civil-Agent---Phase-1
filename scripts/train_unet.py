"""U-Net wall segmentation training loop with synthetic noise augmentation.

This is the integration point for Gap 1: the augmentation pipeline is wired
into the training dataloader so every epoch sees fresh noise combinations.

The script is intentionally minimal — it reads image/mask pairs from a
directory layout::

    data/train/images/<id>.png
    data/train/masks/<id>.png
    data/val/images/<id>.png
    data/val/masks/<id>.png

and trains a U-Net from ``segmentation_models_pytorch``. Model weights and
training hyperparameters live in a YAML config.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from src.cv.augmentation import build_training_augmentation

try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset

    _HAS_TORCH = True
except ImportError:  # pragma: no cover
    _HAS_TORCH = False


class FloorPlanDataset(Dataset if _HAS_TORCH else object):  # type: ignore[misc]
    """Image/mask pair dataset with on-the-fly augmentation."""

    def __init__(
        self,
        root: Path,
        split: str,
        augment: bool = True,
        heavy: bool = False,
        img_size: int = 512,
    ) -> None:
        self.root = Path(root) / split
        self.img_dir = self.root / "images"
        self.mask_dir = self.root / "masks"
        self.ids = sorted(p.stem for p in self.img_dir.glob("*.png"))
        self.img_size = img_size
        self.augmentor = build_training_augmentation(heavy=heavy) if augment else None

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int):  # type: ignore[override]
        stem = self.ids[idx]
        img = cv2.imread(str(self.img_dir / f"{stem}.png"))
        mask = cv2.imread(str(self.mask_dir / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
        img = cv2.resize(img, (self.img_size, self.img_size))
        mask = cv2.resize(mask, (self.img_size, self.img_size), interpolation=cv2.INTER_NEAREST)

        if self.augmentor is not None:
            out = self.augmentor(image=img, mask=mask)
            img, mask = out["image"], out["mask"]

        img_t = torch.from_numpy(img.transpose(2, 0, 1)).float() / 255.0
        mask_t = torch.from_numpy(mask.astype(np.int64))
        return img_t, mask_t


def build_model(num_classes: int = 2) -> "torch.nn.Module":
    import segmentation_models_pytorch as smp

    return smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",
        in_channels=3,
        classes=num_classes,
    )


def train(
    data_root: str,
    epochs: int = 20,
    batch_size: int = 8,
    lr: float = 1e-3,
    device: str = "cuda",
    heavy_aug: bool = False,
    out_dir: str = "data/models/wall_unet",
) -> None:
    if not _HAS_TORCH:
        raise RuntimeError("PyTorch is required for training; install the 'ml' extra.")

    train_ds = FloorPlanDataset(data_root, "train", augment=True, heavy=heavy_aug)
    val_ds = FloorPlanDataset(data_root, "val", augment=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)

    model = build_model().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    best_iou = 0.0
    for epoch in range(epochs):
        model.train()
        t0 = time.time()
        epoch_loss = 0.0
        for imgs, masks in train_loader:
            imgs = imgs.to(device)
            masks = masks.to(device)
            logits = model(imgs)
            loss = F.cross_entropy(logits, masks)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())

        iou = _evaluate(model, val_loader, device)
        if iou > best_iou:
            best_iou = iou
            torch.save(model.state_dict(), out_path / "wall_unet_best.pt")
        print(
            f"epoch={epoch} loss={epoch_loss / len(train_loader):.4f} "
            f"val_iou={iou:.4f} elapsed={time.time() - t0:.1f}s"
        )


@torch.no_grad()  # type: ignore[misc]
def _evaluate(model, loader, device) -> float:
    model.eval()
    inter, union = 0, 0
    for imgs, masks in loader:
        imgs, masks = imgs.to(device), masks.to(device)
        pred = model(imgs).argmax(dim=1)
        inter += int(((pred == 1) & (masks == 1)).sum().item())
        union += int(((pred == 1) | (masks == 1)).sum().item())
    return inter / max(union, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--heavy-aug", action="store_true")
    ap.add_argument("--out-dir", default="data/models/wall_unet")
    args = ap.parse_args()
    train(**vars(args))


if __name__ == "__main__":
    main()
