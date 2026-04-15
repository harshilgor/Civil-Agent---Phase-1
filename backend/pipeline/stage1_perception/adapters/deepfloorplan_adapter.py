"""TF2 DeepFloorplan: subprocess or isolated TF session; 512×512, BGR→RGB."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from ...core.registry import registry
from ...core.schemas import ModelBoundaryOutput, ModelRoomOutput, UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import ModelLoadError, require_dependency, resolve_module, resolve_weights_path


@registry.register("deepfloorplan")
class DeepFloorplanAdapter(BasePerceptionAdapter):
    def __init__(self) -> None:
        self.model: Any | None = None
        self._tf: Any | None = None
        self._predict_fn: Any | None = None
        self._convert_one_hot: Any | None = None
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None
        self.tensorflow_version = ""

    def load(self, weights_path: str | None = None) -> None:
        resolved = resolve_module(
            vendor_path="vendors/tf2_deepfloorplan",
            local_module_candidates=("dfp",),
            external_module_candidates=("dfp",),
        )
        chosen_weights = weights_path or "vendors/tf2_deepfloorplan/weights"
        weights = resolve_weights_path(chosen_weights, require_file=False)
        tf = require_dependency("tensorflow")
        net_module = __import__("dfp.net", fromlist=["deepfloorplanModel"])
        deploy_module = __import__("dfp.deploy", fromlist=["predict"])
        data_module = __import__("dfp.data", fromlist=["convert_one_hot_to_image"])
        if not hasattr(net_module, "deepfloorplanModel"):
            raise ModelLoadError("DeepFloorplan module missing deepfloorplanModel.")
        if not hasattr(deploy_module, "predict"):
            raise ModelLoadError("DeepFloorplan deploy module missing predict().")
        if not hasattr(data_module, "convert_one_hot_to_image"):
            raise ModelLoadError("DeepFloorplan data module missing convert_one_hot_to_image().")

        model_cfg = SimpleNamespace(
            feature_channels=[256, 128, 64, 32],
            backbone="vgg16",
            feature_names=[
                "block1_pool",
                "block2_pool",
                "block3_pool",
                "block4_pool",
                "block5_pool",
            ],
        )
        model = getattr(net_module, "deepfloorplanModel")(config=model_cfg)
        _ = model(tf.zeros((1, 512, 512, 3), dtype=tf.float32))
        ckpt = tf.train.Checkpoint(model=model)
        ckpt.restore(str(weights / "log" / "store" / "G")).expect_partial()
        model.trainable = False

        self.model = model
        self._tf = tf
        self._predict_fn = getattr(deploy_module, "predict")
        self._convert_one_hot = getattr(data_module, "convert_one_hot_to_image")
        self.model_source = resolved.source
        self.model_module = resolved.module_name
        self.weights_path = weights
        self.tensorflow_version = str(getattr(tf, "__version__", "unknown"))

    def predict(self, rgb: Any, *args: Any, **kwargs: Any) -> Any:
        if self.weights_path is None or self.model is None or self._tf is None:
            raise ModelLoadError("DeepFloorplan model is not loaded.")

        arr = np.asarray(rgb)
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], 3, axis=2)
        if arr.ndim != 3:
            raise ModelLoadError(f"DeepFloorplan expects HxWxC input, got shape={arr.shape}")
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.shape[2] > 3:
            arr = arr[..., :3]
        if arr.dtype != np.uint8:
            arr = arr.astype(np.float32)
            if arr.max() <= 1.0:
                arr = np.clip(arr * 255.0, 0, 255)
            arr = arr.astype(np.uint8)

        tf = self._tf
        shp = arr.shape
        img = tf.convert_to_tensor(arr, dtype=tf.uint8)
        img = tf.image.resize(img, [512, 512])
        img = tf.cast(img, dtype=tf.float32) / 255.0
        img = tf.reshape(img, [-1, 512, 512, 3])

        logits_cw, logits_r = self._predict_fn(self.model, img, shp)
        logits_r = tf.image.resize(logits_r, shp[:2])
        logits_cw = tf.image.resize(logits_cw, shp[:2])
        room_idx = self._convert_one_hot(logits_r)[0].numpy().squeeze().astype(np.uint8)
        boundary_idx = self._convert_one_hot(logits_cw)[0].numpy().squeeze().astype(np.uint8)
        boundary_mask = (boundary_idx > 0).astype(np.uint8)

        return {
            "room_logits": logits_r.numpy()[0],
            "room_mask": room_idx,
            "boundary_logits": logits_cw.numpy()[0],
            "boundary_mask": boundary_mask,
            "input_size": tuple(int(v) for v in shp[:2]),
        }

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        diagnostics: dict[str, Any] = {}
        room_output = ModelRoomOutput()
        boundary_output = ModelBoundaryOutput()
        if isinstance(raw, dict) and "error" not in raw:
            room_output.room_logits = raw.get("room_logits")
            room_output.labels = [str(int(c)) for c in np.unique(raw.get("room_mask", np.array([])))]
            boundary_output.boundary_logits = raw.get("boundary_logits")
            boundary_output.wall_mask = raw.get("boundary_mask")
            diagnostics = {"input_size": raw.get("input_size")}
        elif isinstance(raw, dict):
            diagnostics = raw
        elif isinstance(raw, Exception):
            diagnostics = {"error": str(raw)}

        if self.weights_path is not None:
            diagnostics.setdefault("deepfloorplan_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("deepfloorplan_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("deepfloorplan_model_source", self.model_source)
        if self.tensorflow_version:
            diagnostics.setdefault("deepfloorplan_tensorflow_version", self.tensorflow_version)

        return UnifiedPerceptionOutput(
            deepfloorplan_rooms=room_output,
            deepfloorplan_boundaries=boundary_output,
            diagnostics=diagnostics,
        )
