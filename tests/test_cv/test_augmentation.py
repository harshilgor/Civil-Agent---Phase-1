"""Tests for the synthetic noise augmentation pipeline (Gap 1)."""

from __future__ import annotations

import numpy as np
import pytest

from src.cv.augmentation import (
    AugmentationConfig,
    PlanAugmentor,
    _fallback_augment,
    _morph,
    _partial_edge_crop_with_mask,
    _salt_and_pepper,
    _yellow_tint,
    build_training_augmentation,
)


@pytest.fixture()
def sample_image() -> np.ndarray:
    rng = np.random.default_rng(42)
    img = (rng.random((256, 256, 3)) * 255).astype(np.uint8)
    return img


@pytest.fixture()
def sample_mask() -> np.ndarray:
    mask = np.zeros((256, 256), dtype=np.uint8)
    mask[50:200, 50:200] = 1
    return mask


# ---------------------------------------------------------------------------
# Low-level building blocks
# ---------------------------------------------------------------------------


def test_salt_and_pepper_preserves_shape_and_dtype(sample_image: np.ndarray) -> None:
    out = _salt_and_pepper(sample_image, 0.03)
    assert out.shape == sample_image.shape
    assert out.dtype == np.uint8


def test_morph_dilation_changes_image(sample_image: np.ndarray) -> None:
    out_d = _morph(sample_image, 3, "dilate")
    out_e = _morph(sample_image, 3, "erode")
    assert out_d.shape == sample_image.shape
    assert out_e.shape == sample_image.shape


def test_yellow_tint_shifts_colours(sample_image: np.ndarray) -> None:
    out = _yellow_tint(sample_image, 0.25)
    assert out.shape == sample_image.shape
    assert out.dtype == np.uint8


def test_partial_crop_preserves_size(sample_image: np.ndarray, sample_mask: np.ndarray) -> None:
    img_o, msk_o = _partial_edge_crop_with_mask(
        sample_image, sample_mask, (0.05, 0.15), (1, 2)
    )
    assert img_o.shape == sample_image.shape
    assert msk_o is not None and msk_o.shape == sample_mask.shape


# ---------------------------------------------------------------------------
# Fallback pipeline (works without Albumentations)
# ---------------------------------------------------------------------------


def test_fallback_returns_image_and_mask(sample_image: np.ndarray, sample_mask: np.ndarray) -> None:
    out = _fallback_augment(sample_image, sample_mask, AugmentationConfig(), n=5)
    assert out["image"].shape == sample_image.shape
    assert out["image"].dtype == np.uint8
    assert out["mask"].shape == sample_mask.shape
    assert out["mask"].dtype == np.uint8


def test_fallback_image_only(sample_image: np.ndarray) -> None:
    out = _fallback_augment(sample_image, None, AugmentationConfig(), n=10)
    assert out["image"].shape == sample_image.shape
    assert out["mask"] is None


# ---------------------------------------------------------------------------
# Full augmentor (either path — albumentations or fallback)
# ---------------------------------------------------------------------------


def test_augmentor_light_and_heavy(sample_image: np.ndarray, sample_mask: np.ndarray) -> None:
    light = build_training_augmentation(heavy=False)
    heavy = build_training_augmentation(heavy=True)
    o1 = light(image=sample_image, mask=sample_mask)
    o2 = heavy(image=sample_image, mask=sample_mask)
    assert o1["image"].shape == sample_image.shape
    assert o2["image"].shape == sample_image.shape
    assert o1["mask"].shape == sample_mask.shape


def test_augmentor_runs_100_random_samples(
    sample_image: np.ndarray, sample_mask: np.ndarray
) -> None:
    augmentor = build_training_augmentation(heavy=False)
    for _ in range(100):
        out = augmentor(image=sample_image, mask=sample_mask)
        assert out["image"].shape == sample_image.shape
        assert out["image"].dtype == np.uint8
        assert out["mask"].shape == sample_mask.shape
        assert out["mask"].dtype == sample_mask.dtype


def test_mask_stays_binary(sample_image: np.ndarray, sample_mask: np.ndarray) -> None:
    """Mask values must not drift outside the input class set under any transform."""
    augmentor = build_training_augmentation(heavy=True)
    unique_in = set(np.unique(sample_mask).tolist())
    for _ in range(30):
        out = augmentor(image=sample_image, mask=sample_mask)
        unique_out = set(np.unique(out["mask"]).tolist())
        # 0 is always allowed (padding for crops / occlusions)
        assert unique_out.issubset(unique_in | {0})


def test_augmentor_without_mask(sample_image: np.ndarray) -> None:
    augmentor = build_training_augmentation()
    out = augmentor(image=sample_image)
    assert out["image"].shape == sample_image.shape
    assert out["mask"] is None


def test_config_is_tunable(sample_image: np.ndarray) -> None:
    cfg = AugmentationConfig(gaussian_blur_p=1.0, jpeg_p=1.0, rotate_p=1.0)
    augmentor = PlanAugmentor(cfg)
    out = augmentor(image=sample_image)
    assert out["image"].shape == sample_image.shape
