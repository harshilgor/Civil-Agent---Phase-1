"""Shared data contracts for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineMode(str, Enum):
    LIGHT = "light"
    DEEP = "deep"


@dataclass
class ImageTensor:
    """Normalized image array metadata (channels-last RGB unless noted)."""

    data: Any  # numpy ndarray
    scale: float = 1.0
    original_shape: tuple[int, int] | None = None


@dataclass
class ModelRoomOutput:
    """Per-model room segmentation / logits."""

    room_logits: Any | None = None
    polygons: list[Any] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)


@dataclass
class ModelBoundaryOutput:
    """Per-model wall / boundary predictions."""

    boundary_logits: Any | None = None
    wall_mask: Any | None = None


@dataclass
class Edge:
    """Graph edge for vector floor plans."""

    start: tuple[float, float]
    end: tuple[float, float]
    confidence: float = 1.0


@dataclass
class UnifiedPerceptionOutput:
    """Aggregated stage-1 outputs passed to fusion."""

    cubicasa_rooms: ModelRoomOutput | None = None
    cubicasa_boundaries: ModelBoundaryOutput | None = None
    deepfloorplan_rooms: ModelRoomOutput | None = None
    deepfloorplan_boundaries: ModelBoundaryOutput | None = None
    raster_to_graph_edges: list[Edge] = field(default_factory=list)
    floorplan_transform_edges: list[Edge] = field(default_factory=list)
    roomformer_polygons: list[Any] = field(default_factory=list)
    polyroom_polygons: list[Any] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
