"""Tests for :mod:`src.core.geometry.config`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.geometry.config import (
    DEFAULT_CONFIG_PATH,
    GeometryPostProcessConfig,
    SnapConfig,
)
from src.schema.enums import RoomType


class TestDefaults:
    def test_bare_defaults_are_self_consistent(self):
        cfg = GeometryPostProcessConfig()
        assert cfg.snap.angular_tolerance_deg == 5.0
        assert cfg.snap.endpoint_weld_mm == 50.0
        assert cfg.corners.stub_wall_mm == 150.0
        assert cfg.rooms.minimum_area_m2 == 1.0
        assert cfg.grid.minimum_support_walls == 3
        assert cfg.columns.required_score == 0.5
        assert RoomType.STAIRWELL in cfg.cores.seed_room_types

    def test_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            SnapConfig(angular_tolerance_deg=5.0, nonexistent_field=1.0)


class TestLoader:
    def test_loads_shipped_default_yaml(self):
        cfg = GeometryPostProcessConfig.load(DEFAULT_CONFIG_PATH)
        assert cfg.schema_version == "1.0.0"
        # Sanity-check every section is populated.
        assert cfg.snap.axis_cluster_mm == 75.0
        assert cfg.corners.junction_radius_mm == 150.0
        assert cfg.rooms.minimum_area_m2 == 1.0
        assert cfg.grid.minimum_support_walls == 3
        assert cfg.columns.signal_weights.cad_column == 1.0
        assert RoomType.MECHANICAL in cfg.cores.seed_room_types

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            GeometryPostProcessConfig.load(tmp_path / "does_not_exist.yaml")

    def test_load_rejects_unknown_top_level_key(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            'schema_version: "1.0.0"\nzephyr: 42\n', encoding="utf-8"
        )
        with pytest.raises(ValidationError):
            GeometryPostProcessConfig.load(path)

    def test_load_rejects_wrong_schema_version(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text('schema_version: "0.0.1"\n', encoding="utf-8")
        with pytest.raises(ValidationError):
            GeometryPostProcessConfig.load(path)

    def test_load_rejects_empty_cores_seed_list(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            'schema_version: "1.0.0"\ncores:\n  seed_room_types: []\n',
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            GeometryPostProcessConfig.load(path)
