"""Threshold + consistency check (light mode)."""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np

from ...core.schemas import Edge, UnifiedPerceptionOutput

def _largest_components(mask: np.ndarray, max_regions: int = 64) -> list[np.ndarray]:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    comps: list[list[tuple[int, int]]] = []
    for y in range(h):
        for x in range(w):
            if visited[y, x] or mask[y, x] == 0:
                continue
            q: deque[tuple[int, int]] = deque([(y, x)])
            visited[y, x] = True
            pts: list[tuple[int, int]] = []
            while q:
                cy, cx = q.popleft()
                pts.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if ny < 0 or nx < 0 or ny >= h or nx >= w:
                        continue
                    if visited[ny, nx] or mask[ny, nx] == 0:
                        continue
                    visited[ny, nx] = True
                    q.append((ny, nx))
            if len(pts) >= 64:
                comps.append(pts)

    comps.sort(key=len, reverse=True)
    out: list[np.ndarray] = []
    for pts in comps[:max_regions]:
        ys = [p[0] for p in pts]
        xs = [p[1] for p in pts]
        out.append(np.array([[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]], dtype=np.float32))
    return out


def _edges_from_boundary(boundary_mask: np.ndarray, step: int = 16) -> list[Edge]:
    h, w = boundary_mask.shape
    edges: list[Edge] = []
    # Horizontal scans
    for y in range(0, h, step):
        xs = np.where(boundary_mask[y] > 0)[0]
        if xs.size >= 2:
            edges.append(Edge(start=(float(xs.min()), float(y)), end=(float(xs.max()), float(y)), confidence=0.6))
    # Vertical scans
    for x in range(0, w, step):
        ys = np.where(boundary_mask[:, x] > 0)[0]
        if ys.size >= 2:
            edges.append(Edge(start=(float(x), float(ys.min())), end=(float(x), float(ys.max())), confidence=0.6))
    return edges


def light_fuse(perception: UnifiedPerceptionOutput) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"mode": "light"}

    room_logits = None
    if perception.cubicasa_rooms is not None:
        room_logits = perception.cubicasa_rooms.room_logits
    if room_logits is None and perception.deepfloorplan_rooms is not None:
        room_logits = perception.deepfloorplan_rooms.room_logits

    boundary_mask = None
    if perception.deepfloorplan_boundaries is not None:
        boundary_mask = perception.deepfloorplan_boundaries.wall_mask
    if boundary_mask is None and perception.cubicasa_boundaries is not None:
        boundary_mask = perception.cubicasa_boundaries.wall_mask

    rooms: list[dict[str, Any]] = []
    boundaries: list[Edge] = []

    if room_logits is not None:
        rm = np.asarray(room_logits)
        if rm.ndim == 3:
            # CubiCasa: CxHxW, DeepFloorplan: HxWxC
            if rm.shape[0] <= 32 and rm.shape[1] > 32 and rm.shape[2] > 32:
                room_mask = np.argmax(rm, axis=0).astype(np.uint8)
            else:
                room_mask = np.argmax(rm, axis=-1).astype(np.uint8)
        else:
            room_mask = rm.astype(np.uint8)

        comps = _largest_components(room_mask > 0, max_regions=64)
        for idx, poly in enumerate(comps):
            cx = int(np.clip(np.mean(poly[:, 0]), 0, room_mask.shape[1] - 1))
            cy = int(np.clip(np.mean(poly[:, 1]), 0, room_mask.shape[0] - 1))
            label_idx = int(room_mask[cy, cx])
            rooms.append(
                {
                    "id": f"room-{idx+1}",
                    "label": f"class_{label_idx}",
                    "polygon": [
                        {"x": float(x), "y": float(y)} for x, y in poly
                    ],
                    "confidence": 0.65,
                }
            )
        diagnostics["room_regions"] = len(rooms)
    else:
        diagnostics["room_warning"] = "No room logits available from perception stage."

    if boundary_mask is not None:
        bm = np.asarray(boundary_mask).astype(np.uint8)
        if bm.max() <= 1:
            bm = bm * 255
        boundaries = _edges_from_boundary(bm > 0, step=16)
        diagnostics["boundary_edges"] = len(boundaries)
    else:
        diagnostics["boundary_warning"] = "No boundary mask available from perception stage."

    return {
        "rooms": rooms,
        "boundaries": boundaries,
        "diagnostics": diagnostics,
    }
