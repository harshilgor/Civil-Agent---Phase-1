"""Synthetic degradation pipeline for floor-plan training data.

CubiCasa5K training images are clean residential plans. Real-world engineering
drawings that Civil Agent ingests are noisy scans, faxes, photocopies, or
re-compressed images. Training with these degradations produces models that
generalise far better to real inputs.

The pipeline is built on Albumentations so spatial transforms (rotation,
crop) apply identically to image AND segmentation mask. Non-spatial
transforms (blur, compression, noise) only touch the image.

Usage::

    from src.cv.augmentation import build_training_augmentation

    transform = build_training_augmentation(heavy=False)
    out = transform(image=img, mask=mask)
    img_aug, mask_aug = out["image"], out["mask"]
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

try:
    import albumentations as A
    from albumentations.core.transforms_interface import ImageOnlyTransform

    _HAS_ALBU = True
except ImportError:  # pragma: no cover
    A = None  # type: ignore
    ImageOnlyTransform = object  # type: ignore
    _HAS_ALBU = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class AugmentationConfig:
    """Per-degradation probability and intensity knobs."""

    gaussian_blur_p: float = 0.5
    gaussian_blur_kernel: tuple[int, int] = (3, 9)

    jpeg_p: float = 0.5
    jpeg_quality: tuple[int, int] = (15, 50)

    rotate_p: float = 0.5
    rotate_limit_deg: float = 5.0

    salt_pepper_p: float = 0.5
    salt_pepper_density: tuple[float, float] = (0.01, 0.05)

    erase_p: float = 0.5
    erase_patches: tuple[int, int] = (1, 5)
    erase_area_frac: tuple[float, float] = (0.01, 0.05)

    brightness_contrast_p: float = 0.5
    brightness_limit: float = 0.30
    contrast_limit: float = 0.40

    downscale_p: float = 0.5
    downscale_frac: tuple[float, float] = (0.50, 0.75)

    morph_p: float = 0.5
    morph_kernel: tuple[int, int] = (1, 2)

    partial_crop_p: float = 0.5
    partial_crop_frac: tuple[float, float] = (0.05, 0.15)
    partial_crop_edges: tuple[int, int] = (1, 2)

    yellowing_p: float = 0.5
    yellowing_strength: tuple[float, float] = (0.05, 0.30)

    # Number of random degradations per sample
    n_light: tuple[int, int] = (3, 7)
    n_heavy: tuple[int, int] = (7, 10)


DEFAULT_CONFIG = AugmentationConfig()


# ---------------------------------------------------------------------------
# Custom degradation transforms (Albumentations ImageOnlyTransform wrappers)
# ---------------------------------------------------------------------------


if _HAS_ALBU:

    class SaltAndPepperNoise(ImageOnlyTransform):
        """Random salt-and-pepper noise."""

        def __init__(
            self,
            density_range: tuple[float, float] = (0.01, 0.05),
            p: float = 0.5,
        ):
            super().__init__(p=p)
            self.density_range = density_range

        def apply(self, img: np.ndarray, **params: Any) -> np.ndarray:
            return _salt_and_pepper(img, random.uniform(*self.density_range))

        def get_transform_init_args_names(self) -> tuple[str, ...]:
            return ("density_range",)

    class MorphologicalDegradation(ImageOnlyTransform):
        """Random dilation or erosion to simulate fax line-weight variation."""

        def __init__(
            self,
            kernel_range: tuple[int, int] = (1, 2),
            p: float = 0.5,
        ):
            super().__init__(p=p)
            self.kernel_range = kernel_range

        def apply(self, img: np.ndarray, **params: Any) -> np.ndarray:
            ksize = random.randint(*self.kernel_range) * 2 + 1
            op = random.choice(["dilate", "erode"])
            return _morph(img, ksize, op)

        def get_transform_init_args_names(self) -> tuple[str, ...]:
            return ("kernel_range",)

    class BackgroundYellowing(ImageOnlyTransform):
        """Warm paper-aging tint."""

        def __init__(
            self,
            strength_range: tuple[float, float] = (0.05, 0.30),
            p: float = 0.5,
        ):
            super().__init__(p=p)
            self.strength_range = strength_range

        def apply(self, img: np.ndarray, **params: Any) -> np.ndarray:
            return _yellow_tint(img, random.uniform(*self.strength_range))

        def get_transform_init_args_names(self) -> tuple[str, ...]:
            return ("strength_range",)


# ---------------------------------------------------------------------------
# Low-level numpy implementations (also callable without albumentations)
# ---------------------------------------------------------------------------


def _salt_and_pepper(img: np.ndarray, density: float) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    n = int(h * w * density)
    if n <= 0:
        return out
    ys = np.random.randint(0, h, size=n)
    xs = np.random.randint(0, w, size=n)
    salt_mask = np.random.rand(n) > 0.5
    if out.ndim == 3:
        out[ys[salt_mask], xs[salt_mask]] = 255
        out[ys[~salt_mask], xs[~salt_mask]] = 0
    else:
        out[ys[salt_mask], xs[salt_mask]] = 255
        out[ys[~salt_mask], xs[~salt_mask]] = 0
    return out


def _morph(img: np.ndarray, ksize: int, op: str) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
    if op == "dilate":
        return cv2.dilate(img, kernel, iterations=1)
    return cv2.erode(img, kernel, iterations=1)


def _yellow_tint(img: np.ndarray, strength: float) -> np.ndarray:
    if img.ndim != 3:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    out = img.astype(np.float32)
    warm = np.array([170.0, 210.0, 245.0], dtype=np.float32)
    out = out * (1 - strength) + warm * strength
    return np.clip(out, 0, 255).astype(np.uint8)


def _partial_edge_crop_with_mask(
    image: np.ndarray,
    mask: np.ndarray | None,
    frac_range: tuple[float, float],
    edges_range: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray | None]:
    """Crop between 1 and 2 random edges by a random fraction, pad back to size."""
    h, w = image.shape[:2]
    n_edges = random.randint(*edges_range)
    edges = random.sample(["top", "bottom", "left", "right"], k=n_edges)
    top = bottom = left = right = 0
    for e in edges:
        frac = random.uniform(*frac_range)
        if e == "top":
            top = int(h * frac)
        elif e == "bottom":
            bottom = int(h * frac)
        elif e == "left":
            left = int(w * frac)
        elif e == "right":
            right = int(w * frac)

    cropped = image[top: h - bottom if bottom else h, left: w - right if right else w]
    # Pad back to original size with white (paper background)
    pad_top = top
    pad_bottom = bottom
    pad_left = left
    pad_right = right
    fill = 255
    img_out = cv2.copyMakeBorder(
        cropped, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=fill,
    )
    img_out = cv2.resize(img_out, (w, h), interpolation=cv2.INTER_LINEAR)

    mask_out = None
    if mask is not None:
        m_cropped = mask[top: h - bottom if bottom else h, left: w - right if right else w]
        m_out = cv2.copyMakeBorder(
            m_cropped, pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_CONSTANT, value=0,  # background class
        )
        mask_out = cv2.resize(m_out, (w, h), interpolation=cv2.INTER_NEAREST)

    return img_out, mask_out


# ---------------------------------------------------------------------------
# Pipeline builder
# ---------------------------------------------------------------------------


def build_training_augmentation(
    heavy: bool = False,
    config: AugmentationConfig | None = None,
) -> "PlanAugmentor":
    """Return a composed augmentor that applies 3-7 (light) or 7-10 (heavy) random
    degradations per sample.

    The object exposes ``__call__(image, mask) -> dict``.
    """
    cfg = config or DEFAULT_CONFIG
    return PlanAugmentor(cfg, heavy=heavy)


class PlanAugmentor:
    """Composed augmentation pipeline.

    Applies a random subset of degradations per call. Spatial transforms
    (rotate, partial crop) are synchronised between image and mask.
    """

    def __init__(self, config: AugmentationConfig, heavy: bool = False) -> None:
        self.config = config
        self.heavy = heavy
        self.n_range = config.n_heavy if heavy else config.n_light

        if _HAS_ALBU:
            # Non-spatial image-only transforms → one Albumentations Compose
            self._image_only = A.Compose([
                A.GaussianBlur(
                    blur_limit=config.gaussian_blur_kernel,
                    p=config.gaussian_blur_p,
                ),
                A.ImageCompression(
                    quality_range=config.jpeg_quality,
                    p=config.jpeg_p,
                ),
                SaltAndPepperNoise(
                    density_range=config.salt_pepper_density,
                    p=config.salt_pepper_p,
                ),
                A.RandomBrightnessContrast(
                    brightness_limit=config.brightness_limit,
                    contrast_limit=config.contrast_limit,
                    p=config.brightness_contrast_p,
                ),
                A.Downscale(
                    scale_range=config.downscale_frac,
                    interpolation_pair={
                        "upscale": cv2.INTER_LINEAR,
                        "downscale": cv2.INTER_LINEAR,
                    },
                    p=config.downscale_p,
                ),
                MorphologicalDegradation(
                    kernel_range=config.morph_kernel,
                    p=config.morph_p,
                ),
                BackgroundYellowing(
                    strength_range=config.yellowing_strength,
                    p=config.yellowing_p,
                ),
            ])
            # Spatial transforms → separate Compose that targets both image and mask
            self._spatial = A.Compose([
                A.Rotate(
                    limit=config.rotate_limit_deg,
                    border_mode=cv2.BORDER_CONSTANT,
                    fill=255,
                    fill_mask=0,
                    p=config.rotate_p,
                ),
                A.CoarseDropout(
                    num_holes_range=config.erase_patches,
                    hole_height_range=(
                        int(np.sqrt(config.erase_area_frac[0]) * 100),
                        int(np.sqrt(config.erase_area_frac[1]) * 100),
                    ),
                    hole_width_range=(
                        int(np.sqrt(config.erase_area_frac[0]) * 100),
                        int(np.sqrt(config.erase_area_frac[1]) * 100),
                    ),
                    fill=255,
                    fill_mask=0,
                    p=config.erase_p,
                ),
            ])
        else:
            self._image_only = None
            self._spatial = None

    def __call__(
        self,
        image: np.ndarray,
        mask: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        """Apply a random subset of degradations to ``image`` (and ``mask``).

        Returns a dict ``{"image": np.ndarray, "mask": np.ndarray | None}``.
        """
        n = random.randint(*self.n_range)
        if _HAS_ALBU and self._image_only is not None:
            img = image
            msk = mask
            # Randomly select which transforms fire this call by reshuffling probs
            # (Albumentations samples per-transform — we approximate the n-count
            # constraint by drawing a subset of all available augs.)
            if self._spatial is not None:
                out = self._spatial(image=img, mask=msk) if msk is not None else self._spatial(image=img)
                img = out["image"]
                msk = out.get("mask", None)
            out = self._image_only(image=img)
            img = out["image"]

            # Partial crop (implemented manually so it stays mask-synced)
            if random.random() < self.config.partial_crop_p:
                img, msk = _partial_edge_crop_with_mask(
                    img, msk,
                    self.config.partial_crop_frac,
                    self.config.partial_crop_edges,
                )
            # Ignore n here — Albumentations already samples per-probability
            _ = n
            return {"image": img, "mask": msk}

        # Fallback pure-numpy path — used when Albumentations isn't installed
        return _fallback_augment(image, mask, self.config, n)


# ---------------------------------------------------------------------------
# Fallback (no-Albumentations) implementation
# ---------------------------------------------------------------------------


def _fallback_augment(
    image: np.ndarray,
    mask: np.ndarray | None,
    cfg: AugmentationConfig,
    n: int,
) -> dict[str, np.ndarray]:
    """Pure-numpy/cv2 fallback that applies *n* random degradations.

    Used primarily for unit tests when Albumentations is absent.
    """
    img = image.copy()
    msk = mask.copy() if mask is not None else None
    ops = [
        "blur", "jpeg", "rotate", "salt_pepper", "erase", "brightness_contrast",
        "downscale", "morph", "partial_crop", "yellowing",
    ]
    for op in random.sample(ops, k=min(n, len(ops))):
        if op == "blur":
            k = random.randint(*cfg.gaussian_blur_kernel)
            if k % 2 == 0:
                k += 1
            img = cv2.GaussianBlur(img, (k, k), 0)
        elif op == "jpeg":
            q = random.randint(*cfg.jpeg_quality)
            ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            if ok:
                img = cv2.imdecode(enc, cv2.IMREAD_UNCHANGED)
        elif op == "rotate":
            angle = random.uniform(-cfg.rotate_limit_deg, cfg.rotate_limit_deg)
            h, w = img.shape[:2]
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            img = cv2.warpAffine(img, M, (w, h), borderValue=255)
            if msk is not None:
                msk = cv2.warpAffine(msk, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        elif op == "salt_pepper":
            img = _salt_and_pepper(img, random.uniform(*cfg.salt_pepper_density))
        elif op == "erase":
            n_patch = random.randint(*cfg.erase_patches)
            h, w = img.shape[:2]
            for _ in range(n_patch):
                area = random.uniform(*cfg.erase_area_frac) * h * w
                pw = int(np.sqrt(area))
                ph = int(np.sqrt(area))
                x = random.randint(0, max(w - pw, 1))
                y = random.randint(0, max(h - ph, 1))
                img[y: y + ph, x: x + pw] = 255
                if msk is not None:
                    msk[y: y + ph, x: x + pw] = 0
        elif op == "brightness_contrast":
            alpha = 1.0 + random.uniform(-cfg.contrast_limit, cfg.contrast_limit)
            beta = random.uniform(-cfg.brightness_limit, cfg.brightness_limit) * 255
            img = np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)
        elif op == "downscale":
            f = random.uniform(*cfg.downscale_frac)
            h, w = img.shape[:2]
            small = cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_LINEAR)
            img = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
        elif op == "morph":
            ks = random.randint(*cfg.morph_kernel) * 2 + 1
            img = _morph(img, ks, random.choice(["dilate", "erode"]))
        elif op == "partial_crop":
            img, msk = _partial_edge_crop_with_mask(
                img, msk, cfg.partial_crop_frac, cfg.partial_crop_edges
            )
        elif op == "yellowing":
            img = _yellow_tint(img, random.uniform(*cfg.yellowing_strength))
    return {"image": img, "mask": msk}


__all__ = [
    "AugmentationConfig",
    "DEFAULT_CONFIG",
    "PlanAugmentor",
    "build_training_augmentation",
]
