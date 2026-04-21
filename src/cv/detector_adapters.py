"""Concrete detector adapters for the Step-8 ML engine.

The :class:`~src.cv.ml_engine.MLEngine` speaks to detectors through two
thin Protocols: :class:`WallSegmenterAdapter` and
:class:`SymbolDetectorAdapter`.  Every checkpoint architecture the
manifest knows about ships a pair of concrete implementations here:

================  =========================  ===========================
Architecture      Wall adapter                Symbol adapter
================  =========================  ===========================
``cubicasa_hg``   :class:`CubiCasaHgWallAdapter`    —
``smp_unet``      :class:`SmpUnetWallAdapter`       —
``yolov8_seg``    :class:`YoloSegWallAdapter`       —
``yolov8``        —                           :class:`YoloSymbolAdapter`
================  =========================  ===========================

Two hard rules:

* **No heavy imports at module import time.**  ``torch`` /
  ``segmentation_models_pytorch`` / ``ultralytics`` are imported lazily
  inside the adapters' ``segment`` / ``detect`` methods, so a test run
  that only exercises the engine's dispatch logic with injected fakes
  never pays the torch-import cost.

* **Adapters are dumb transformers.**  They consume a BGR ``np.ndarray``
  and emit a :class:`WallSegmentationOutput` or a list of
  :class:`SymbolDetection`.  All manifest-aware concerns (provenance,
  fallback selection, completeness scoring) live one layer up in
  :class:`~src.cv.ml_engine.MLEngine`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

import numpy as np
import structlog

from backend.weights.loader import ResolvedWeights
from backend.weights.manifest import Architecture

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared output contracts
# ---------------------------------------------------------------------------


# Heatmap indices expected from CubiCasa's split_prediction() output.  See
# ``vendors/cubicasa/floortrans/post_prosessing.py::split_prediction`` — the
# first 13 heatmap channels are wall-type heatmaps, channels 13-21 are
# opening heatmaps (doors / windows), the 12 room channels are softmaxed
# separately.  We keep the magic numbers here (not on the engine) because
# they are a property of that specific checkpoint's head geometry.
_CUBICASA_WALL_HEATMAPS = slice(0, 13)
# Vendor post-processor ships this default for the binarisation threshold.
# Exposed as a class attr so tests can override.
_CUBICASA_WALL_THRESHOLD = 0.03
# The SMP U-Net head trained on CubiCasa5K follows the 17-class layout used
# by :mod:`src.cv.wall_segmenter` — class 1 is ``wall``.
_SMP_WALL_CLASS_INDEX = 1


@dataclass(frozen=True)
class WallSegmentationOutput:
    """What every :class:`WallSegmenterAdapter` emits.

    Attributes:
        wall_mask: ``uint8`` binary mask of wall pixels (0 / 255) at the
            original image resolution.
        element_masks: optional mapping of class-name → binary mask, for
            downstream consumers (rooms, openings, etc.) that want to
            reuse the segmenter's multi-class output without re-running
            the model.  Keys depend on the architecture; callers must
            not assume any particular set of keys is present.
        confidence: self-reported model confidence in the range
            ``[0.0, 1.0]``.  Not a calibrated probability — it is the
            signal the engine uses to decide whether to engage the
            fallback wall segmenter.  Exactly how each adapter computes
            it is documented on the adapter itself.
    """

    wall_mask: np.ndarray
    element_masks: dict[str, np.ndarray] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass(frozen=True)
class SymbolDetection:
    """A single YOLO-style bounding-box prediction."""

    class_name: str
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 — inclusive
    confidence: float


# ---------------------------------------------------------------------------
# Protocols — the engine only talks to these
# ---------------------------------------------------------------------------


@runtime_checkable
class WallSegmenterAdapter(Protocol):
    """Any object that can turn a BGR image into wall pixels."""

    def segment(self, image: np.ndarray) -> WallSegmentationOutput: ...


@runtime_checkable
class SymbolDetectorAdapter(Protocol):
    """Any object that can detect door/window/stair symbols in an image."""

    def detect(self, image: np.ndarray) -> list[SymbolDetection]: ...


# ---------------------------------------------------------------------------
# CubiCasa hourglass (primary wall segmenter for the residential slot)
# ---------------------------------------------------------------------------


class CubiCasaHgWallAdapter:
    """Wrap the CubiCasa hourglass for use as a :class:`WallSegmenterAdapter`.

    The model is constructed up-front by
    :func:`backend.weights.loader.WeightsLoader.build_model` and passed in
    already warmed.  The adapter is responsible only for the
    preprocess → forward → split_prediction → mask-extraction dance —
    see ``backend/pipeline/stage1_perception/adapters/cubicasa_adapter.py``
    for the upstream reference implementation this follows.

    Confidence signal
    =================

    We report the **mean wall-heatmap score over pixels classified as
    walls** — *not* the wall-pixel fraction of the image.  The pixel
    fraction is a geometric property of the plan (a denser plan produces
    more wall pixels regardless of model quality); the mean heatmap
    score is a *trust* signal: "how strong was the model's belief about
    the pixels it chose to call walls".

    CubiCasa's wall heatmaps are **not** softmaxed (only the room and
    icon channels are — see ``split_prediction`` in the vendor
    post-processor), so the score scale is model-specific.  Empirically:

        * 0.03 is the vendor's per-pixel wall threshold — any pixel
          above this is classified as a wall.
        * Healthy residential plans yield mean-on-wall scores in roughly
          ``[0.1, 0.6]``.
        * A score near or below the per-pixel threshold signals the
          heatmap barely cleared the bar → the engine should engage
          the fallback.

    The primary-vs-fallback threshold lives on the manifest entry
    (``confidence_threshold`` on :class:`WeightsEntry`) so it can be
    retuned per checkpoint without a code change.
    """

    def __init__(
        self,
        model: Any,
        *,
        split_prediction: Any,
        target_height: int = 512,
        wall_threshold: float = _CUBICASA_WALL_THRESHOLD,
        n_rooms: int = 12,
        n_icons: int = 11,
    ) -> None:
        self._model = model
        self._split_prediction = split_prediction
        self._target_height = int(target_height)
        self._wall_threshold = float(wall_threshold)
        self._n_rooms = int(n_rooms)
        self._n_icons = int(n_icons)
        # CubiCasa head width = 21 heatmaps + n_rooms + n_icons.
        self._heatmap_channels = 21

    def segment(self, image: np.ndarray) -> WallSegmentationOutput:
        import torch  # noqa: PLC0415 — keep torch lazy

        rgb = _bgr_to_rgb(image)
        arr = rgb.astype(np.float32) / 255.0
        orig_h, orig_w = arr.shape[:2]

        target_h = self._target_height
        # Match upstream: round width so the resized image's width is
        # divisible by 32, which is what the hourglass expects.
        target_w = max(
            64,
            int(round(orig_w * (target_h / max(orig_h, 1)) / 32.0) * 32),
        )
        resized = _resize_bilinear(arr, target_w, target_h)

        tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0)
        tensor = tensor * 2.0 - 1.0  # [-1, 1] input range
        with torch.no_grad():
            pred = self._model(tensor)
        heatmaps, rooms, icons = self._split_prediction(
            pred.cpu(),
            (target_h, target_w),
            [self._heatmap_channels, self._n_rooms, self._n_icons],
        )

        wall_score = np.max(heatmaps[_CUBICASA_WALL_HEATMAPS], axis=0)
        wall_mask_small = (wall_score > self._wall_threshold).astype(np.uint8)

        # Upsample back to the original image resolution.  We use a nearest
        # resize on the binarised mask to avoid introducing spurious mid-
        # tones along wall edges — the downstream vectoriser assumes crisp
        # edges.
        wall_mask = _resize_nearest(wall_mask_small, orig_w, orig_h) * 255

        # Room mask: argmax over the 12 softmaxed room channels, upsampled
        # back.  Exposed as ``element_masks["room_<idx>"]`` so downstream
        # callers can pull per-class masks without re-running the model.
        room_argmax_small = np.argmax(rooms, axis=0).astype(np.uint8)
        room_argmax = _resize_nearest(room_argmax_small, orig_w, orig_h)
        element_masks = {"rooms_argmax": room_argmax}

        # Icon argmax — Channel C's opening extractor reuses these.
        icon_argmax_small = np.argmax(icons, axis=0).astype(np.uint8)
        icon_argmax = _resize_nearest(icon_argmax_small, orig_w, orig_h)
        element_masks["icons_argmax"] = icon_argmax

        # Confidence: mean heatmap score over pixels classified as walls.
        # See the class docstring for the rationale — geometric
        # wall-pixel fraction would be a worse signal.
        wall_bool = wall_mask_small.astype(bool)
        if wall_bool.any():
            confidence = float(wall_score[wall_bool].mean())
        else:
            # No pixel cleared the per-pixel threshold → no walls found.
            # Report zero so the engine engages the fallback.
            confidence = 0.0

        logger.info(
            "cubicasa_hg_wall_segmented",
            orig_size=(orig_h, orig_w),
            model_size=(target_h, target_w),
            wall_pixel_fraction=round(float(wall_bool.mean()), 4),
            mean_heatmap_score=round(confidence, 4),
        )
        return WallSegmentationOutput(
            wall_mask=wall_mask,
            element_masks=element_masks,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# SMP U-Net (alternative wall segmenter for the commercial slot)
# ---------------------------------------------------------------------------


class SmpUnetWallAdapter:
    """Wrap a ``segmentation_models_pytorch.Unet`` head.

    Confidence: the mean softmax score of the winning class over the
    wall pixels.  This is a calibrated-ish probability because the SMP
    head applies softmax over the class axis; empirically values lie in
    ``[0.0, 0.95]`` with trained weights.
    """

    def __init__(
        self,
        model: Any,
        *,
        input_size: tuple[int, int] = (512, 512),
        wall_class_index: int = _SMP_WALL_CLASS_INDEX,
        element_class_names: Optional[dict[int, str]] = None,
    ) -> None:
        self._model = model
        self._input_size = tuple(input_size)
        self._wall_class_index = int(wall_class_index)
        self._element_class_names = dict(element_class_names or {})

    def segment(self, image: np.ndarray) -> WallSegmentationOutput:
        import torch  # noqa: PLC0415
        import torch.nn.functional as F  # noqa: PLC0415

        rgb = _bgr_to_rgb(image)
        orig_h, orig_w = rgb.shape[:2]
        target_w, target_h = self._input_size
        resized = _resize_bilinear(
            rgb.astype(np.float32) / 255.0, target_w, target_h
        )

        tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0).float()
        with torch.no_grad():
            logits = self._model(tensor)
            probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()

        # Argmax for the class map, max prob for confidence.
        pred = np.argmax(probs, axis=0).astype(np.uint8)
        wall_mask_small = (pred == self._wall_class_index).astype(np.uint8)
        wall_mask = _resize_nearest(wall_mask_small, orig_w, orig_h) * 255

        element_masks: dict[str, np.ndarray] = {}
        for class_idx, class_name in self._element_class_names.items():
            if class_idx == self._wall_class_index:
                continue
            mask_small = (pred == class_idx).astype(np.uint8)
            if not mask_small.any():
                continue
            element_masks[class_name] = (
                _resize_nearest(mask_small, orig_w, orig_h) * 255
            )

        # Mean probability of the winning class over wall pixels.  Fall
        # back to zero when the mask is empty so the engine treats it as
        # "detector produced nothing" → fallback engages.
        if wall_mask_small.any():
            wall_probs = probs[self._wall_class_index][wall_mask_small.astype(bool)]
            confidence = float(wall_probs.mean())
        else:
            confidence = 0.0

        logger.info(
            "smp_unet_wall_segmented",
            orig_size=(orig_h, orig_w),
            wall_pixel_fraction=round(float(wall_mask_small.mean()), 4),
            mean_wall_prob=round(confidence, 4),
        )
        return WallSegmentationOutput(
            wall_mask=wall_mask,
            element_masks=element_masks,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# YOLOv8-Seg (wall fallback)
# ---------------------------------------------------------------------------


class YoloSegWallAdapter:
    """Wrap an Ultralytics YOLO-Seg model for wall-mask fallback.

    Confidence: the max per-instance confidence across returned wall
    masks, or 0.0 when no instances pass the threshold.
    """

    def __init__(
        self,
        model: Any,
        *,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        imgsz: int = 1024,
        wall_class_names: tuple[str, ...] = ("wall",),
    ) -> None:
        self._model = model
        self._conf = float(conf_threshold)
        self._iou = float(iou_threshold)
        self._imgsz = int(imgsz)
        self._wall_names = tuple(n.lower() for n in wall_class_names)

    def segment(self, image: np.ndarray) -> WallSegmentationOutput:
        orig_h, orig_w = image.shape[:2]
        results = self._model(
            image,
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            verbose=False,
        )

        wall_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
        best_confidence = 0.0
        for result in results:
            masks = getattr(result, "masks", None)
            boxes = getattr(result, "boxes", None)
            if masks is None or boxes is None or len(boxes) == 0:
                continue
            names = getattr(result, "names", {}) or {}
            mask_data = masks.data.cpu().numpy()  # (N, h, w)
            for idx in range(mask_data.shape[0]):
                class_id = int(boxes.cls[idx])
                class_name = str(names.get(class_id, "")).lower()
                if self._wall_names and class_name not in self._wall_names:
                    continue
                instance_conf = float(boxes.conf[idx])
                instance_mask_small = (mask_data[idx] > 0.5).astype(np.uint8)
                instance_mask = _resize_nearest(
                    instance_mask_small, orig_w, orig_h
                )
                wall_mask = np.maximum(wall_mask, instance_mask)
                best_confidence = max(best_confidence, instance_conf)

        logger.info(
            "yolo_seg_wall_segmented",
            orig_size=(orig_h, orig_w),
            best_instance_confidence=round(best_confidence, 4),
            wall_pixel_fraction=round(float(wall_mask.mean()), 4),
        )
        return WallSegmentationOutput(
            wall_mask=wall_mask * 255,
            element_masks={},
            confidence=best_confidence,
        )


# ---------------------------------------------------------------------------
# YOLOv8 symbol detector
# ---------------------------------------------------------------------------


class YoloSymbolAdapter:
    """Wrap an Ultralytics YOLO detection model for architectural symbols.

    The class-name list defaults to the Phase 1 symbol taxonomy
    (doors, windows, stairs, elevators) and can be overridden when a
    different checkpoint uses a different class ordering.
    """

    def __init__(
        self,
        model: Any,
        *,
        class_names: Optional[list[str]] = None,
        conf_threshold: float = 0.30,
        iou_threshold: float = 0.50,
        imgsz: int = 1024,
    ) -> None:
        self._model = model
        self._class_names = list(class_names) if class_names else None
        self._conf = float(conf_threshold)
        self._iou = float(iou_threshold)
        self._imgsz = int(imgsz)

    def detect(self, image: np.ndarray) -> list[SymbolDetection]:
        results = self._model(
            image,
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            verbose=False,
        )
        detections: list[SymbolDetection] = []
        for result in results:
            names = self._class_names or (getattr(result, "names", {}) or {})
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                if isinstance(names, dict):
                    class_name = str(names.get(cls_id, f"class_{cls_id}"))
                elif cls_id < len(names):
                    class_name = names[cls_id]
                else:
                    class_name = f"class_{cls_id}"
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    SymbolDetection(
                        class_name=class_name,
                        bbox=(round(x1), round(y1), round(x2), round(y2)),
                        confidence=round(float(box.conf[0]), 3),
                    )
                )
        logger.info("yolo_symbols_detected", count=len(detections))
        return detections


# ---------------------------------------------------------------------------
# Factories — dispatch on Architecture so the engine stays architecture-blind
# ---------------------------------------------------------------------------


def build_wall_adapter(
    resolved: ResolvedWeights, model: Any, *, split_prediction: Any = None
) -> WallSegmenterAdapter:
    """Construct the right wall-segmenter adapter for ``resolved``'s architecture.

    ``split_prediction`` must be provided for the CubiCasa path; the
    loader will typically pass ``floortrans.post_prosessing.split_prediction``
    — keeping the dependency injected avoids pulling the vendor tree
    into :mod:`src.cv.detector_adapters` at import time.
    """

    arch = resolved.architecture
    params = resolved.params
    if arch is Architecture.CUBICASA_HG:
        if split_prediction is None:
            raise ValueError(
                "CubiCasa HG adapter requires the vendor split_prediction() "
                "function; pass it through the engine."
            )
        return CubiCasaHgWallAdapter(
            model,
            split_prediction=split_prediction,
            n_rooms=int(params.get("n_rooms", 12)),
            n_icons=int(params.get("n_icons", 11)),
        )
    if arch is Architecture.SMP_UNET:
        imgsz = int(params.get("imgsz", 512))
        # Wall class index for SMP U-Net defaults to 1 (upstream 17-class
        # layout), overridable per checkpoint via ``params.wall_class``.
        wall_class = int(params.get("wall_class", _SMP_WALL_CLASS_INDEX))
        return SmpUnetWallAdapter(
            model,
            input_size=(imgsz, imgsz),
            wall_class_index=wall_class,
        )
    if arch is Architecture.YOLOV8_SEG:
        return YoloSegWallAdapter(
            model,
            conf_threshold=float(params.get("conf_threshold", 0.25)),
            iou_threshold=float(params.get("iou_threshold", 0.45)),
            imgsz=int(params.get("imgsz", 1024)),
        )
    raise ValueError(
        f"Architecture {arch!r} does not back a wall segmenter. "
        "Expected one of: cubicasa_hg, smp_unet, yolov8_seg."
    )


def build_symbol_adapter(
    resolved: ResolvedWeights, model: Any
) -> SymbolDetectorAdapter:
    """Construct the right symbol-detector adapter for ``resolved``.

    Only ``yolov8`` is supported today.  When Phase 1 gains a second
    symbol architecture (e.g. a transformer-based detector), add its
    branch here; no call site needs to change.
    """

    arch = resolved.architecture
    params = resolved.params
    if arch is Architecture.YOLOV8:
        return YoloSymbolAdapter(
            model,
            class_names=list(params.get("classes") or []) or None,
            conf_threshold=float(params.get("conf_threshold", 0.30)),
            iou_threshold=float(params.get("iou_threshold", 0.50)),
            imgsz=int(params.get("imgsz", 1024)),
        )
    raise ValueError(
        f"Architecture {arch!r} does not back a symbol detector. "
        "Expected: yolov8."
    )


# ---------------------------------------------------------------------------
# Image-ops helpers — kept private and numpy-only so importing this module
# does not drag cv2 into processes that only test dispatch logic.
# ---------------------------------------------------------------------------


def _bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    """Return an HxWx3 RGB array from a possibly-grayscale BGR input."""

    if image.ndim == 2:
        return np.repeat(image[..., None], 3, axis=2)
    if image.ndim == 3 and image.shape[2] >= 3:
        # BGR → RGB; ignore any alpha channel.
        return image[..., :3][..., ::-1]
    raise ValueError(f"Unsupported image shape for segmentation: {image.shape}")


def _resize_bilinear(arr: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """Bilinear resize that does not pull OpenCV.

    Uses PIL so torch tests that import this module without cv2 still work.
    Loses a tiny amount of fidelity versus ``cv2.resize`` but the
    segmenter head is trained at 512 px and is insensitive to resampler
    choice at this scale.
    """

    from PIL import Image  # noqa: PLC0415

    if arr.ndim == 3:
        uint = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        pil = Image.fromarray(uint, mode="RGB")
        resized = pil.resize((new_w, new_h), Image.BILINEAR)
        return np.asarray(resized, dtype=np.float32) / 255.0
    uint = arr.astype(np.uint8)
    pil = Image.fromarray(uint, mode="L")
    resized = pil.resize((new_w, new_h), Image.BILINEAR)
    return np.asarray(resized, dtype=np.uint8)


def _resize_nearest(arr: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """Nearest-neighbour resize for binary / argmax masks."""

    from PIL import Image  # noqa: PLC0415

    pil = Image.fromarray(arr.astype(np.uint8), mode="L")
    resized = pil.resize((new_w, new_h), Image.NEAREST)
    return np.asarray(resized, dtype=np.uint8)


__all__ = [
    "WallSegmentationOutput",
    "SymbolDetection",
    "WallSegmenterAdapter",
    "SymbolDetectorAdapter",
    "CubiCasaHgWallAdapter",
    "SmpUnetWallAdapter",
    "YoloSegWallAdapter",
    "YoloSymbolAdapter",
    "build_wall_adapter",
    "build_symbol_adapter",
]
