"""Configuration schema for the Step-9 geometry post-processor.

Every tuning knob for snapping, corner resolution, room extraction,
grid inference, column scoring, and core detection lives in this
module.  The defaults mirror ``config/geometry_postprocess.yaml`` so
downstream code can construct a :class:`GeometryPostProcessConfig`
without reading the yaml (convenient for tests, never shipped in a
production path).

The loader is strict: unknown sections or fields raise.  Adding a knob
means touching this file, the yaml, and a test — by design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from src.schema.enums import RoomType

# ---------------------------------------------------------------------------
# Path to the default yaml.  Resolved at import time so tests can
# monkey-patch it if they need a custom config file layout.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "geometry_postprocess.yaml"

CONFIG_SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Per-pass configs.  Kept as separate BaseModels so validation errors
# pinpoint the offending section.
# ---------------------------------------------------------------------------


class SnapConfig(BaseModel):
    model_config = {"extra": "forbid"}

    angular_tolerance_deg: float = Field(default=5.0, gt=0.0, le=45.0)
    endpoint_weld_mm: float = Field(default=50.0, gt=0.0)
    axis_cluster_mm: float = Field(default=75.0, gt=0.0)
    preserve_diagonals: bool = True


class CornerConfig(BaseModel):
    model_config = {"extra": "forbid"}

    junction_radius_mm: float = Field(default=150.0, gt=0.0)
    stub_wall_mm: float = Field(default=150.0, gt=0.0)
    max_endpoint_shift_mm: float = Field(default=250.0, gt=0.0)


class RoomConfig(BaseModel):
    model_config = {"extra": "forbid"}

    minimum_area_m2: float = Field(default=1.0, gt=0.0)
    hole_threshold_m2: float = Field(default=0.5, gt=0.0)
    simplification_mm: float = Field(default=50.0, ge=0.0)


class GridConfig(BaseModel):
    model_config = {"extra": "forbid"}

    minimum_support_walls: int = Field(default=3, ge=1)
    minimum_support_length_mm: float = Field(default=2000.0, gt=0.0)
    cluster_tolerance_mm: float = Field(default=250.0, gt=0.0)
    min_bay_span_mm: float = Field(default=1500.0, gt=0.0)


class ColumnSignalWeights(BaseModel):
    model_config = {"extra": "forbid"}

    wall_endpoint: float = Field(default=0.55, ge=0.0, le=2.0)
    short_wall: float = Field(default=0.35, ge=0.0, le=2.0)
    cad_column: float = Field(default=1.0, ge=0.0, le=2.0)


class ColumnConfig(BaseModel):
    model_config = {"extra": "forbid"}

    grid_proximity_mm: float = Field(default=300.0, gt=0.0)
    short_wall_max_mm: float = Field(default=500.0, gt=0.0)
    cad_promotion_mm: float = Field(default=150.0, gt=0.0)
    required_score: float = Field(default=0.5, ge=0.0, le=1.0)
    signal_weights: ColumnSignalWeights = Field(
        default_factory=ColumnSignalWeights
    )


class CoreConfig(BaseModel):
    model_config = {"extra": "forbid"}

    seed_room_types: list[RoomType] = Field(
        default_factory=lambda: [
            RoomType.STAIRWELL,
            RoomType.ELEVATOR,
            RoomType.BATHROOM,
            RoomType.MECHANICAL,
        ]
    )
    adjacency_tolerance_mm: float = Field(default=100.0, gt=0.0)
    minimum_cluster_area_m2: float = Field(default=2.0, gt=0.0)
    simplification_mm: float = Field(default=50.0, ge=0.0)

    @field_validator("seed_room_types")
    @classmethod
    def _non_empty(cls, v: list[RoomType]) -> list[RoomType]:
        if not v:
            raise ValueError("cores.seed_room_types must contain at least one room type")
        return v


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class GeometryPostProcessConfig(BaseModel):
    """Full configuration for the Step-9 geometry post-processor.

    Load from yaml with :meth:`GeometryPostProcessConfig.load`, or
    construct in-process for tests with the defaults baked into each
    sub-config.
    """

    model_config = {"extra": "forbid"}

    schema_version: str = Field(default=CONFIG_SCHEMA_VERSION)
    snap: SnapConfig = Field(default_factory=SnapConfig)
    corners: CornerConfig = Field(default_factory=CornerConfig)
    rooms: RoomConfig = Field(default_factory=RoomConfig)
    grid: GridConfig = Field(default_factory=GridConfig)
    columns: ColumnConfig = Field(default_factory=ColumnConfig)
    cores: CoreConfig = Field(default_factory=CoreConfig)

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v != CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"geometry_postprocess config schema_version must be "
                f"{CONFIG_SCHEMA_VERSION}, got {v!r}"
            )
        return v

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "GeometryPostProcessConfig":
        """Load and validate the yaml at *path* (or the default).

        Raises :class:`FileNotFoundError` if the file is missing and
        :class:`pydantic.ValidationError` for schema violations.
        """

        config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.model_validate(data)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DEFAULT_CONFIG_PATH",
    "ColumnConfig",
    "ColumnSignalWeights",
    "CoreConfig",
    "CornerConfig",
    "GeometryPostProcessConfig",
    "GridConfig",
    "RoomConfig",
    "SnapConfig",
]
