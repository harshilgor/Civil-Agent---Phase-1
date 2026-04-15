"""RoomFormer: density map from boundary fusion (256×256), polygon extraction."""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from ...core.registry import registry
from ...core.schemas import UnifiedPerceptionOutput
from ..base_adapter import BasePerceptionAdapter
from ..load_utils import repo_root
from ..load_utils import ModelLoadError, resolve_source_without_import, resolve_weights_path


@registry.register("roomformer")
class RoomFormerAdapter(BasePerceptionAdapter):
    def __init__(self) -> None:
        self.model: Any | None = None
        self._torch: Any | None = None
        self.model_source = ""
        self.model_module = ""
        self.weights_path: Path | None = None

    def load(self, weights_path: str | None = None) -> None:
        source = resolve_source_without_import("vendors/roomformer/models")
        chosen_weights = weights_path or "vendors/roomformer/checkpoints/roomformer_stru3d.pth"
        weights = resolve_weights_path(chosen_weights, require_file=True)
        vendor_root = repo_root() / "vendors" / "roomformer"
        if str(vendor_root) not in sys.path:
            sys.path.insert(0, str(vendor_root))

        torch = __import__("torch")
        spec = importlib.util.spec_from_file_location(
            "roomformer_models",
            vendor_root / "models" / "__init__.py",
            submodule_search_locations=[str(vendor_root / "models")],
        )
        if spec is None or spec.loader is None:
            raise ModelLoadError("Unable to create module spec for RoomFormer models.")
        model_module = importlib.util.module_from_spec(spec)
        sys.modules["roomformer_models"] = model_module
        spec.loader.exec_module(model_module)
        if not hasattr(model_module, "build_model"):
            raise ModelLoadError("RoomFormer models package missing build_model().")

        model_args = SimpleNamespace(
            backbone="resnet50",
            lr_backbone=0.0,
            dilation=False,
            position_embedding="sine",
            position_embedding_scale=2 * np.pi,
            num_feature_levels=4,
            enc_layers=6,
            dec_layers=6,
            dim_feedforward=1024,
            hidden_dim=256,
            dropout=0.1,
            nheads=8,
            num_queries=800,
            num_polys=20,
            dec_n_points=4,
            enc_n_points=4,
            query_pos_type="sine",
            with_poly_refine=True,
            masked_attn=False,
            semantic_classes=-1,
            aux_loss=True,
            device="cpu",
            set_cost_class=2,
            set_cost_coords=5,
            cls_loss_coef=2,
            room_cls_loss_coef=0.2,
            coords_loss_coef=5,
            raster_loss_coef=1,
        )
        model = getattr(model_module, "build_model")(model_args, train=False)
        checkpoint = torch.load(str(weights), map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["model"], strict=False)
        model.eval()

        self.model = model
        self._torch = torch
        self.model_source = source
        self.model_module = "roomformer.models"
        self.weights_path = weights

    def predict(self, density_map: Any, *args: Any, **kwargs: Any) -> Any:
        if self.weights_path is None or self.model is None or self._torch is None:
            raise ModelLoadError("RoomFormer model is not loaded.")
        torch = self._torch

        arr = np.asarray(density_map)
        if arr.ndim == 3:
            arr = arr[..., 0]
        if arr.ndim != 2:
            raise ModelLoadError(f"RoomFormer expects 2D density map, got shape={arr.shape}")
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        if arr.max() > 1.0:
            arr /= 255.0
        arr = np.clip(arr, 0.0, 1.0)

        sample = torch.from_numpy(arr).unsqueeze(0)  # [1, H, W]
        with torch.no_grad():
            outputs = self.model([sample])
        pred_logits = outputs["pred_logits"][0]
        pred_coords = outputs["pred_coords"][0]
        fg_mask = torch.sigmoid(pred_logits) > 0.5

        polygons: list[list[list[int]]] = []
        for room_idx in range(fg_mask.shape[0]):
            valid = pred_coords[room_idx][fg_mask[room_idx]]
            if valid.numel() == 0:
                continue
            corners = torch.round(valid * 255.0).int().cpu().numpy()
            if len(corners) < 4:
                continue
            try:
                if Polygon(corners).area < 100:
                    continue
            except Exception:
                continue
            polygons.append(corners.tolist())

        return {
            "pred_logits": pred_logits.cpu().numpy(),
            "pred_coords": pred_coords.cpu().numpy(),
            "polygons": polygons,
            "polygon_count": len(polygons),
        }

    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        diagnostics: dict[str, Any] = {}
        polygons: list[Any] = []
        if isinstance(raw, dict) and "error" not in raw:
            polygons = raw.get("polygons", [])
            diagnostics = {"polygon_count": raw.get("polygon_count", len(polygons))}
        elif isinstance(raw, dict):
            diagnostics = raw
        elif isinstance(raw, Exception):
            diagnostics = {"error": str(raw)}
        if self.weights_path is not None:
            diagnostics.setdefault("roomformer_weights_path", str(self.weights_path))
        if self.model_module:
            diagnostics.setdefault("roomformer_model_module", self.model_module)
        if self.model_source:
            diagnostics.setdefault("roomformer_model_source", self.model_source)
        return UnifiedPerceptionOutput(roomformer_polygons=polygons, diagnostics=diagnostics)
