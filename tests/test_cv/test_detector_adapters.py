"""Unit tests for the Step-8 detector adapters.

Each adapter wraps an ML model (torch / ultralytics).  Instead of
loading real checkpoints — which would require torch, a GPU, and
hundreds of MB of weights — we hand the adapters a fake model object
that returns pre-baked tensors or box lists.  The tests then assert
the adapter massages those into the expected
:class:`WallSegmentationOutput` / :class:`SymbolDetection` shape.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.weights.loader import ResolvedWeights
from backend.weights.manifest import Architecture, WeightsEntry, WeightsSource
from src.cv.detector_adapters import (
    CubiCasaHgWallAdapter,
    SmpUnetWallAdapter,
    SymbolDetection,
    WallSegmentationOutput,
    YoloSegWallAdapter,
    YoloSymbolAdapter,
    build_symbol_adapter,
    build_wall_adapter,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bgr_image() -> np.ndarray:
    """Synthetic 128x160 BGR image — deliberately rectangular so tests
    catch any aspect-ratio bug where a square is silently stretched."""

    img = np.full((128, 160, 3), 255, dtype=np.uint8)
    img[30:90, 40:120, :] = 0  # a dark central block so adapters have
    # something to detect (even though the fakes ignore the input).
    return img


def _make_resolved(
    name: str,
    arch: Architecture,
    *,
    params: dict[str, Any] | None = None,
    num_classes: int | None = None,
) -> ResolvedWeights:
    """Build a ResolvedWeights without any filesystem IO — tests use
    this when they need to exercise ``build_wall_adapter`` /
    ``build_symbol_adapter``.
    """

    from pathlib import Path

    entry = WeightsEntry(
        architecture=arch,
        model_id=name,
        model_version="0.1.0",
        filename=f"{name}.bin",
        source=WeightsSource(local_path=Path(f"{name}.bin")),
        num_classes=num_classes,
        params=params or {},
    )
    return ResolvedWeights(
        name=name,
        entry=entry,
        path=Path(f"/tmp/{name}.bin"),
        manifest_hash="a" * 64,
    )


# ===========================================================================
# CubiCasa HG
# ===========================================================================


class TestCubiCasaHgWallAdapter:
    """Drive the adapter with a fake torch model + fake split_prediction."""

    @pytest.fixture()
    def wall_heatmap_stack(self) -> np.ndarray:
        """(21, 64, 80) heatmaps where only channel 0 has signal."""

        stack = np.zeros((21, 64, 80), dtype=np.float32)
        # Paint a mid-image wall in channel 0 above the 0.03 threshold.
        stack[0, 20:40, 30:50] = 0.5
        return stack

    @pytest.fixture()
    def rooms_softmax(self) -> np.ndarray:
        """(12, 64, 80) softmax — class 3 dominates one region."""

        rooms = np.full((12, 64, 80), 0.01, dtype=np.float32)
        rooms[3, 10:30, 10:40] = 0.9
        return rooms

    @pytest.fixture()
    def icons_softmax(self) -> np.ndarray:
        """(11, 64, 80) softmax — class 5 dominates another region."""

        icons = np.full((11, 64, 80), 0.01, dtype=np.float32)
        icons[5, 40:50, 50:70] = 0.8
        return icons

    def test_segment_output_shape_matches_input(
        self,
        bgr_image: np.ndarray,
        wall_heatmap_stack: np.ndarray,
        rooms_softmax: np.ndarray,
        icons_softmax: np.ndarray,
    ):
        # Fake torch model: ignores input, returns a MagicMock with .cpu()
        # that feeds split_prediction.
        fake_model = MagicMock()
        fake_pred = MagicMock()
        fake_pred.cpu.return_value = fake_pred
        fake_model.return_value = fake_pred

        def fake_split(tensor, shape, split):
            assert shape == (512, 640)  # width = 160 * 512/128 rounded to 32 = 640
            assert split == [21, 12, 11]
            return wall_heatmap_stack, rooms_softmax, icons_softmax

        adapter = CubiCasaHgWallAdapter(
            fake_model, split_prediction=fake_split
        )
        out = adapter.segment(bgr_image)

        assert isinstance(out, WallSegmentationOutput)
        # Mask is upsampled back to the ORIGINAL image resolution —
        # the whole point of keeping the original shape around.
        assert out.wall_mask.shape == bgr_image.shape[:2]
        assert out.wall_mask.dtype == np.uint8
        # Wall pixels came from the synthetic heatmap, so some non-zero
        # fraction must make it through the threshold + upsample.
        assert (out.wall_mask == 255).sum() > 0
        # Background remains zero.
        assert (out.wall_mask == 0).sum() > 0

    def test_element_masks_include_rooms_and_icons(
        self,
        bgr_image: np.ndarray,
        wall_heatmap_stack: np.ndarray,
        rooms_softmax: np.ndarray,
        icons_softmax: np.ndarray,
    ):
        fake_model = MagicMock()
        fake_pred = MagicMock()
        fake_pred.cpu.return_value = fake_pred
        fake_model.return_value = fake_pred

        adapter = CubiCasaHgWallAdapter(
            fake_model,
            split_prediction=lambda *_a, **_k: (
                wall_heatmap_stack, rooms_softmax, icons_softmax,
            ),
        )
        out = adapter.segment(bgr_image)
        assert "rooms_argmax" in out.element_masks
        assert "icons_argmax" in out.element_masks
        assert out.element_masks["rooms_argmax"].shape == bgr_image.shape[:2]
        assert out.element_masks["icons_argmax"].shape == bgr_image.shape[:2]

    def test_confidence_is_mean_heatmap_score_over_wall_pixels(
        self,
        bgr_image: np.ndarray,
        wall_heatmap_stack: np.ndarray,
        rooms_softmax: np.ndarray,
        icons_softmax: np.ndarray,
    ):
        """Fixture paints a rectangular heatmap patch with a constant
        score of 0.5.  The confidence must therefore be ~0.5 — the
        mean over wall pixels — not the wall-pixel fraction (~0.078).
        """

        fake_model = MagicMock()
        fake_pred = MagicMock()
        fake_pred.cpu.return_value = fake_pred
        fake_model.return_value = fake_pred

        adapter = CubiCasaHgWallAdapter(
            fake_model,
            split_prediction=lambda *_a, **_k: (
                wall_heatmap_stack, rooms_softmax, icons_softmax,
            ),
        )
        out = adapter.segment(bgr_image)
        assert out.confidence == pytest.approx(0.5, abs=0.01)

    def test_confidence_tracks_heatmap_strength(
        self,
        bgr_image: np.ndarray,
        rooms_softmax: np.ndarray,
        icons_softmax: np.ndarray,
    ):
        """A weaker heatmap over the same geometry gives a lower
        confidence, even though the wall-pixel fraction is identical.
        This is the exact regression the fix guards against — a pixel-
        fraction-based confidence could not distinguish these cases.
        """

        weak_stack = np.zeros((21, 64, 80), dtype=np.float32)
        weak_stack[0, 20:40, 30:50] = 0.1  # same geometry, 5x weaker signal
        fake_model = MagicMock()
        fake_pred = MagicMock()
        fake_pred.cpu.return_value = fake_pred
        fake_model.return_value = fake_pred

        adapter = CubiCasaHgWallAdapter(
            fake_model,
            split_prediction=lambda *_a, **_k: (
                weak_stack, rooms_softmax, icons_softmax,
            ),
        )
        out = adapter.segment(bgr_image)
        # Mean-on-wall-pixels = 0.1, not the pixel fraction.
        assert out.confidence == pytest.approx(0.1, abs=0.01)

    def test_confidence_zero_when_heatmap_empty(
        self,
        bgr_image: np.ndarray,
        rooms_softmax: np.ndarray,
        icons_softmax: np.ndarray,
    ):
        fake_model = MagicMock()
        fake_pred = MagicMock()
        fake_pred.cpu.return_value = fake_pred
        fake_model.return_value = fake_pred

        empty_heatmap = np.zeros((21, 64, 80), dtype=np.float32)
        adapter = CubiCasaHgWallAdapter(
            fake_model,
            split_prediction=lambda *_a, **_k: (
                empty_heatmap, rooms_softmax, icons_softmax,
            ),
        )
        out = adapter.segment(bgr_image)
        assert out.confidence == 0.0
        assert (out.wall_mask == 0).all()


# ===========================================================================
# SMP U-Net
# ===========================================================================


class TestSmpUnetWallAdapter:
    def _fake_model_with_logits(self, logits: np.ndarray):
        """Wrap ``logits`` in a fake torch module that returns them as a tensor."""

        import torch

        class _FakeModel:
            def __call__(self, tensor):
                return torch.from_numpy(logits).unsqueeze(0)  # (1, C, H, W)

        return _FakeModel()

    def test_wall_mask_picks_winning_class(self, bgr_image: np.ndarray):
        # 3-class logits: wall (class 1) wins in a central block.
        h, w = 512, 512
        logits = np.zeros((3, h, w), dtype=np.float32)
        logits[0] = 1.0  # background baseline
        logits[1, 100:300, 100:300] = 5.0  # wall wins here
        adapter = SmpUnetWallAdapter(
            self._fake_model_with_logits(logits),
            input_size=(512, 512),
            wall_class_index=1,
        )
        out = adapter.segment(bgr_image)
        assert out.wall_mask.shape == bgr_image.shape[:2]
        # Some pixels must be marked as wall.
        assert (out.wall_mask == 255).sum() > 0
        # Confidence is the mean softmax probability of the winning
        # class over wall pixels — must be > 0.5 since logits were 5
        # vs baseline 1.
        assert out.confidence > 0.5

    def test_returns_zero_confidence_when_wall_class_never_wins(
        self, bgr_image: np.ndarray
    ):
        h, w = 512, 512
        logits = np.zeros((3, h, w), dtype=np.float32)
        logits[0] = 5.0  # background dominates everywhere
        adapter = SmpUnetWallAdapter(
            self._fake_model_with_logits(logits),
            input_size=(512, 512),
            wall_class_index=1,
        )
        out = adapter.segment(bgr_image)
        assert (out.wall_mask == 0).all()
        assert out.confidence == 0.0

    def test_respects_custom_wall_class_index(self, bgr_image: np.ndarray):
        h, w = 512, 512
        logits = np.zeros((4, h, w), dtype=np.float32)
        logits[0] = 1.0
        logits[2, 100:400, 100:400] = 3.0  # class 2 wins centrally
        adapter = SmpUnetWallAdapter(
            self._fake_model_with_logits(logits),
            input_size=(512, 512),
            wall_class_index=2,
        )
        out = adapter.segment(bgr_image)
        assert (out.wall_mask == 255).sum() > 0


# ===========================================================================
# YOLOv8-Seg wall fallback
# ===========================================================================


class _FakeYoloMasks:
    def __init__(self, masks_np: np.ndarray):
        self._data = _FakeTensor(masks_np)

    @property
    def data(self):
        return self._data


class _FakeTensor:
    def __init__(self, arr: np.ndarray):
        self._arr = arr

    def cpu(self):
        return self

    def numpy(self):
        return self._arr

    @property
    def shape(self):
        return self._arr.shape

    def __len__(self):
        return self._arr.shape[0]

    def __getitem__(self, idx):
        return float(self._arr[idx])


class _FakeBoxes:
    def __init__(self, classes: list[int], confs: list[float]):
        self.cls = _FakeTensor(np.array(classes, dtype=np.int64))
        self.conf = _FakeTensor(np.array(confs, dtype=np.float32))

    def __len__(self):
        return len(self.cls._arr)


class _FakeYoloResult:
    def __init__(self, masks_np, classes, confs, names):
        self.masks = _FakeYoloMasks(masks_np) if masks_np is not None else None
        self.boxes = _FakeBoxes(classes, confs) if classes else None
        self.names = names


class TestYoloSegWallAdapter:
    def test_merges_instance_masks_into_single_wall_mask(
        self, bgr_image: np.ndarray
    ):
        # Two wall instances plus a non-wall distractor.  The adapter
        # should union the walls and drop the distractor.
        masks = np.zeros((3, 64, 64), dtype=np.float32)
        masks[0, 10:30, 10:50] = 1.0  # wall #1
        masks[1, 40:60, 20:60] = 1.0  # wall #2
        masks[2, 0:20, 0:20] = 1.0   # non-wall (class "door")

        fake_model = MagicMock(
            return_value=[
                _FakeYoloResult(
                    masks_np=masks,
                    classes=[0, 0, 1],
                    confs=[0.85, 0.72, 0.91],
                    names={0: "wall", 1: "door"},
                )
            ]
        )
        adapter = YoloSegWallAdapter(fake_model)
        out = adapter.segment(bgr_image)
        assert out.wall_mask.shape == bgr_image.shape[:2]
        # Confidence = max conf over wall instances only.
        assert out.confidence == pytest.approx(0.85)

    def test_returns_empty_when_no_instances_pass(
        self, bgr_image: np.ndarray
    ):
        fake_model = MagicMock(
            return_value=[
                _FakeYoloResult(
                    masks_np=None,
                    classes=[],
                    confs=[],
                    names={},
                )
            ]
        )
        adapter = YoloSegWallAdapter(fake_model)
        out = adapter.segment(bgr_image)
        assert out.confidence == 0.0
        assert (out.wall_mask == 0).all()

    def test_forwards_threshold_and_imgsz_to_model(
        self, bgr_image: np.ndarray
    ):
        fake_model = MagicMock(return_value=[])
        adapter = YoloSegWallAdapter(
            fake_model, conf_threshold=0.55, iou_threshold=0.35, imgsz=640
        )
        adapter.segment(bgr_image)
        call_kwargs = fake_model.call_args.kwargs
        assert call_kwargs["conf"] == 0.55
        assert call_kwargs["iou"] == 0.35
        assert call_kwargs["imgsz"] == 640
        assert call_kwargs["verbose"] is False


# ===========================================================================
# YOLOv8 symbol detector
# ===========================================================================


class _FakeXyxy:
    """Matches ``torch.Tensor`` shape enough for the adapter: ``[0].tolist()``."""

    def __init__(self, xyxy: tuple[float, float, float, float]):
        self._xyxy = xyxy

    def tolist(self) -> list[float]:
        return list(self._xyxy)


class _FakeBox:
    def __init__(self, cls_id: int, conf: float, xyxy: tuple[float, float, float, float]):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [_FakeXyxy(xyxy)]


class _FakeYoloDetectResult:
    def __init__(self, boxes: list[_FakeBox], names: dict[int, str]):
        self.boxes = boxes
        self.names = names


class TestYoloSymbolAdapter:
    def test_detect_returns_typed_symbol_detections(
        self, bgr_image: np.ndarray
    ):
        result = _FakeYoloDetectResult(
            boxes=[
                _FakeBox(0, 0.81, (10.0, 20.0, 40.0, 50.0)),
                _FakeBox(1, 0.66, (60.0, 70.0, 80.0, 90.0)),
            ],
            names={0: "door", 1: "window"},
        )
        fake_model = MagicMock(return_value=[result])
        adapter = YoloSymbolAdapter(fake_model)
        detections = adapter.detect(bgr_image)
        assert len(detections) == 2
        assert all(isinstance(d, SymbolDetection) for d in detections)
        assert detections[0].class_name == "door"
        assert detections[0].bbox == (10, 20, 40, 50)
        assert detections[0].confidence == pytest.approx(0.81, abs=0.01)
        assert detections[1].class_name == "window"

    def test_uses_explicit_class_names_over_result_names(
        self, bgr_image: np.ndarray
    ):
        result = _FakeYoloDetectResult(
            boxes=[_FakeBox(2, 0.5, (0, 0, 10, 10))],
            names={2: "from_result"},
        )
        fake_model = MagicMock(return_value=[result])
        adapter = YoloSymbolAdapter(
            fake_model, class_names=["door", "window", "stair", "elevator"]
        )
        detections = adapter.detect(bgr_image)
        assert detections[0].class_name == "stair"

    def test_unknown_class_id_falls_back_to_placeholder_name(
        self, bgr_image: np.ndarray
    ):
        result = _FakeYoloDetectResult(
            boxes=[_FakeBox(99, 0.5, (0, 0, 10, 10))],
            names={},
        )
        fake_model = MagicMock(return_value=[result])
        adapter = YoloSymbolAdapter(fake_model)
        detections = adapter.detect(bgr_image)
        assert detections[0].class_name == "class_99"

    def test_empty_results_returns_empty_list(self, bgr_image: np.ndarray):
        fake_model = MagicMock(return_value=[])
        adapter = YoloSymbolAdapter(fake_model)
        assert adapter.detect(bgr_image) == []


# ===========================================================================
# Factories
# ===========================================================================


class TestBuildWallAdapter:
    def test_cubicasa_hg_requires_split_prediction(self):
        resolved = _make_resolved("cc_hg", Architecture.CUBICASA_HG)
        with pytest.raises(ValueError, match="split_prediction"):
            build_wall_adapter(resolved, MagicMock())

    def test_cubicasa_hg_constructs_adapter(self):
        resolved = _make_resolved(
            "cc_hg",
            Architecture.CUBICASA_HG,
            params={"n_rooms": 12, "n_icons": 11},
        )
        adapter = build_wall_adapter(
            resolved, MagicMock(), split_prediction=lambda *_a, **_k: None
        )
        assert isinstance(adapter, CubiCasaHgWallAdapter)

    def test_smp_unet_constructs_adapter(self):
        resolved = _make_resolved(
            "smp",
            Architecture.SMP_UNET,
            params={"imgsz": 768, "wall_class": 1},
        )
        adapter = build_wall_adapter(resolved, MagicMock())
        assert isinstance(adapter, SmpUnetWallAdapter)

    def test_yolov8_seg_constructs_adapter(self):
        resolved = _make_resolved(
            "yolo",
            Architecture.YOLOV8_SEG,
            params={"conf_threshold": 0.3, "iou_threshold": 0.5, "imgsz": 800},
        )
        adapter = build_wall_adapter(resolved, MagicMock())
        assert isinstance(adapter, YoloSegWallAdapter)

    def test_yolov8_detection_rejected_for_wall_role(self):
        resolved = _make_resolved("yolo_det", Architecture.YOLOV8)
        with pytest.raises(ValueError, match="wall segmenter"):
            build_wall_adapter(resolved, MagicMock())


class TestBuildSymbolAdapter:
    def test_yolov8_constructs_adapter_with_custom_classes(self):
        resolved = _make_resolved(
            "symbols",
            Architecture.YOLOV8,
            params={
                "classes": ["door", "window", "stair"],
                "conf_threshold": 0.25,
                "iou_threshold": 0.6,
                "imgsz": 960,
            },
        )
        adapter = build_symbol_adapter(resolved, MagicMock())
        assert isinstance(adapter, YoloSymbolAdapter)

    def test_non_yolo_rejected_for_symbol_role(self):
        resolved = _make_resolved("wrong", Architecture.SMP_UNET)
        with pytest.raises(ValueError, match="symbol detector"):
            build_symbol_adapter(resolved, MagicMock())
