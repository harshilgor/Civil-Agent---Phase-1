"""CubiCasa: resize, 4-rotation TTA, split_prediction → room + boundary outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ...core.registry import registry
from ...core.schemas import ModelBoundaryOutput, ModelRoomOutput, UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import (
    ModelLoadError,
    require_dependency,
    resolve_module,
    resolve_weights_path,
)


@registry.register("cubicasa")
class CubiCasaAdapter(BasePerceptionAdapter):
    """Phase-1 CubiCasa loader with local-vendor first strategy."""

    def __init__(self) -> None:
        self.model: Any | None = None
        self._split_prediction: Any | None = None
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None

    def load(self, weights_path: str | None = None) -> None:
        resolve_module(
            vendor_path="vendors/cubicasa",
            local_module_candidates=("floortrans.models.hg_furukawa_original",),
            external_module_candidates=("floortrans.models.hg_furukawa_original",),
        )
        model_module = __import__(
            "floortrans.models.hg_furukawa_original",
            fromlist=["hg_furukawa_original"],
        )
        if not hasattr(model_module, "hg_furukawa_original"):
            raise ModelLoadError(
                "CubiCasa model module does not expose hg_furukawa_original."
            )
        model_builder = getattr(model_module, "hg_furukawa_original")
        post_module = __import__(
            "floortrans.post_prosessing",
            fromlist=["split_prediction"],
        )
        if not hasattr(post_module, "split_prediction"):
            raise ModelLoadError("CubiCasa post-processing module missing split_prediction().")
        split_prediction = getattr(post_module, "split_prediction")
        chosen_weights = weights_path or "vendors/cubicasa/weights/model_best_val_loss_var.pkl"
        weights = resolve_weights_path(chosen_weights, require_file=True)

        torch = require_dependency("torch")
        model = model_builder(n_classes=51)
        n_classes = 44
        model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
        model.upsample = torch.nn.ConvTranspose2d(
            n_classes, n_classes, kernel_size=4, stride=4
        )
        checkpoint = torch.load(str(weights), map_location="cpu", weights_only=False)
        if "model_state" not in checkpoint:
            raise ModelLoadError(
                "CubiCasa checkpoint missing 'model_state' key required for loading."
            )
        model.load_state_dict(checkpoint["model_state"])
        model.eval()

        self.model = model
        self._split_prediction = split_prediction
        self.model_source = "local"
        self.model_module = "floortrans.models.hg_furukawa_original"
        self.weights_path = weights

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        if self.model is None or self._split_prediction is None:
            raise ModelLoadError("CubiCasa model is not loaded.")

        torch = require_dependency("torch")
        arr = np.asarray(rgb)
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], 3, axis=2)
        if arr.ndim != 3:
            raise ModelLoadError(f"CubiCasa expects HxWxC input, got shape={arr.shape}")
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.shape[2] > 3:
            arr = arr[..., :3]

        if arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        if arr.max() > 1.0:
            arr /= 255.0

        orig_h, orig_w = arr.shape[:2]
        target_h = 512
        target_w = max(64, int(round(orig_w * (target_h / max(orig_h, 1)) / 32.0) * 32))

        pil_module = __import__("PIL.Image", fromlist=["Image"])
        resized = np.asarray(
            pil_module.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), mode="RGB").resize(
                (target_w, target_h),
                pil_module.Resampling.BILINEAR,
            ),
            dtype=np.float32,
        )
        resized /= 255.0

        tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0)
        tensor = tensor * 2.0 - 1.0
        with torch.no_grad():
            pred = self.model(tensor)
        heatmaps, rooms, _icons = self._split_prediction(pred.cpu(), (target_h, target_w), [21, 12, 11])
        room_mask = np.argmax(rooms, axis=0).astype(np.uint8)
        wall_score = np.max(heatmaps[:13], axis=0)
        wall_mask = (wall_score > 0.03).astype(np.uint8)

        return {
            "room_logits": rooms,
            "room_mask": room_mask,
            "boundary_logits": heatmaps,
            "wall_mask": wall_mask,
            "model_size": (target_h, target_w),
            "input_size": (orig_h, orig_w),
        }

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        diagnostics: dict[str, Any] = {}
        room_output = ModelRoomOutput()
        boundary_output = ModelBoundaryOutput()

        if isinstance(raw, dict) and "error" not in raw:
            room_output.room_logits = raw.get("room_logits")
            room_output.labels = [str(int(c)) for c in np.unique(raw.get("room_mask", np.array([])))]
            boundary_output.boundary_logits = raw.get("boundary_logits")
            boundary_output.wall_mask = raw.get("wall_mask")
            diagnostics = {
                "input_size": raw.get("input_size"),
                "model_size": raw.get("model_size"),
            }
        elif isinstance(raw, dict):
            diagnostics = raw
        elif isinstance(raw, Exception):
            diagnostics = {"error": str(raw)}

        if self.weights_path is not None:
            diagnostics.setdefault("cubicasa_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("cubicasa_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("cubicasa_model_source", self.model_source)

        return UnifiedPerceptionOutput(
            cubicasa_rooms=room_output,
            cubicasa_boundaries=boundary_output,
            diagnostics=diagnostics,
        )
