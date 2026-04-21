"""Shared fixtures for Phase 3 tests.

The fixtures build dict-form building graphs and structural design graphs
that mimic Phase 1/2 outputs. They are deliberately minimal — only the
fields Phase 3 actually consumes are populated.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.phase3.assumptions import AssumptionBuilder
from src.phase3.models.enums import ExposureCategory, MaterialFamily, RiskCategory
from src.phase3.models.inputs import LocationData, Phase3Input


# ---------------------------------------------------------------------------
# Building graph builders
# ---------------------------------------------------------------------------


def _rectangular_facade_polygon(width_mm: float, depth_mm: float) -> list[list[float]]:
    return [
        [0.0, 0.0],
        [width_mm, 0.0],
        [width_mm, depth_mm],
        [0.0, depth_mm],
        [0.0, 0.0],
    ]


def _grid_columns(
    x_positions: list[float], y_positions: list[float], prefix: str = "C"
) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    i = 0
    for y in y_positions:
        for x in x_positions:
            cols.append(
                {
                    "position": [x, y],
                    "grid_intersection": f"{prefix}-{i}",
                    "confidence": 1.0,
                    "is_required": False,
                }
            )
            i += 1
    return cols


def _support_candidates_from_cols(
    cols: list[dict[str, Any]], story_ids: list[str]
) -> list[dict[str, Any]]:
    supports: list[dict[str, Any]] = []
    i = 0
    for story_id in story_ids:
        for col in cols:
            supports.append(
                {
                    "id": f"S{i}-{story_id}",
                    "position": col["position"],
                    "story": story_id,
                    "classification": "preferred",
                    "score": 0.9,
                    "reasons": [],
                    "penalties": [],
                    "grid_intersection": col["grid_intersection"],
                    "is_stacked": True,
                    "stack_group_id": col["grid_intersection"],
                }
            )
            i += 1
    return supports


def _stories(
    n: int, floor_to_floor_mm: float, floor_area_m2: float, usages: list[str] | None = None
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    elevation = 0.0
    for i in range(n):
        usage = (usages[i] if usages else "office") if usages is None or i < len(usages) else "office"
        result.append(
            {
                "id": f"S{i + 1}",
                "level": i + 1,
                "floor_to_floor_mm": floor_to_floor_mm,
                "elevation_mm": elevation,
                "floor_area_gross_m2": floor_area_m2,
                "usage": usage,
            }
        )
        elevation += floor_to_floor_mm
    return result


def _build_office_rc_graph() -> dict[str, Any]:
    width_mm = 4 * 9000.0  # 4 bays x 9 m
    depth_mm = 3 * 8000.0  # 3 bays x 8 m
    floor_to_floor = 3600.0
    n_stories = 8
    floor_area_m2 = (width_mm * depth_mm) / 1_000_000.0

    x_positions = [9000.0 * i for i in range(5)]
    y_positions = [8000.0 * i for i in range(4)]
    columns = _grid_columns(x_positions, y_positions)

    usages = ["office"] * (n_stories - 1) + ["roof_inaccessible"]
    stories = _stories(n_stories, floor_to_floor, floor_area_m2, usages=usages)

    return {
        "project": {
            "name": "test_office_rc",
            "location": {"lat": 41.88, "lng": -87.63, "city": "Chicago", "state": "IL"},
            "occupancy_type": "office",
            "material_preference": "reinforced_concrete",
            "num_stories": n_stories,
            "total_height_mm": floor_to_floor * n_stories,
            "building_code": "ASCE 7-22",
        },
        "stories": stories,
        "grid": {
            "x_lines": [{"id": f"X{i}", "position_mm": x} for i, x in enumerate(x_positions)],
            "y_lines": [{"id": f"Y{i}", "position_mm": y} for i, y in enumerate(y_positions)],
            "bays": [],
        },
        "walls": [],
        "rooms": [],
        "openings": [],
        "column_candidates": columns,
        "cores": [],
        "facade": {
            "perimeter_polygon": _rectangular_facade_polygon(width_mm, depth_mm),
            "perimeter_length_mm": 2 * (width_mm + depth_mm),
        },
        "metadata": {
            "input_source": "structured_form",
            "confidence_scores": {"overall": 0.9},
            "assumptions_made": [],
            "warnings": [],
        },
    }


def _build_residential_steel_graph() -> dict[str, Any]:
    width_mm = 3 * 6000.0
    depth_mm = 3 * 6000.0
    floor_to_floor = 3200.0
    n_stories = 6
    floor_area_m2 = (width_mm * depth_mm) / 1_000_000.0

    x_positions = [6000.0 * i for i in range(4)]
    y_positions = [6000.0 * i for i in range(4)]
    columns = _grid_columns(x_positions, y_positions)

    usages = ["residential"] * (n_stories - 1) + ["roof_inaccessible"]
    stories = _stories(n_stories, floor_to_floor, floor_area_m2, usages=usages)

    return {
        "project": {
            "name": "test_residential_steel",
            "location": {"lat": 34.05, "lng": -118.24, "city": "Los Angeles", "state": "CA"},
            "occupancy_type": "residential",
            "material_preference": "steel",
            "num_stories": n_stories,
            "total_height_mm": floor_to_floor * n_stories,
            "building_code": "ASCE 7-22",
        },
        "stories": stories,
        "grid": {
            "x_lines": [{"id": f"X{i}", "position_mm": x} for i, x in enumerate(x_positions)],
            "y_lines": [{"id": f"Y{i}", "position_mm": y} for i, y in enumerate(y_positions)],
            "bays": [],
        },
        "walls": [],
        "rooms": [],
        "openings": [],
        "column_candidates": columns,
        "cores": [],
        "facade": {
            "perimeter_polygon": _rectangular_facade_polygon(width_mm, depth_mm),
            "perimeter_length_mm": 2 * (width_mm + depth_mm),
        },
        "metadata": {
            "input_source": "structured_form",
            "confidence_scores": {"overall": 0.85},
        },
    }


def _build_structural_graph(bg: dict[str, Any]) -> dict[str, Any]:
    columns = bg["column_candidates"]
    story_ids = [s["id"] for s in bg["stories"]]
    supports = _support_candidates_from_cols(columns, story_ids)
    return {
        "building_graph_id": bg["project"]["name"],
        "zones": [],
        "support_candidates": supports,
        "forbidden_regions": [],
        "vertical_alignment_groups": [],
        "span_map": {
            "spans": [],
            "max_span_mm": 9000.0,
            "min_span_mm": 6000.0,
            "typical_span_mm": 8000.0,
            "span_regularity": 1.0,
        },
        "framing_zones": [],
        "gravity_system_candidates": [],
        "lateral_system_candidates": [],
        "constraints": [],
        "metadata": {
            "processing_time_seconds": 0.1,
            "assumptions_made": [],
            "warnings": [],
            "confidence_overall": 0.85,
            "building_regularity": "regular",
            "recommended_review_items": [],
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_building_graph_office_rc() -> dict[str, Any]:
    """8-story RC office building, 12 m x 9 m grid, Chicago, IL."""

    return _build_office_rc_graph()


@pytest.fixture
def sample_building_graph_residential_steel() -> dict[str, Any]:
    """6-story steel residential, 6 m x 6 m grid, Los Angeles, CA."""

    return _build_residential_steel_graph()


@pytest.fixture
def sample_structural_design_graph(sample_building_graph_office_rc) -> dict[str, Any]:
    """Structural graph matching the office RC fixture."""

    return _build_structural_graph(sample_building_graph_office_rc)


@pytest.fixture
def sample_structural_design_graph_residential(
    sample_building_graph_residential_steel,
) -> dict[str, Any]:
    return _build_structural_graph(sample_building_graph_residential_steel)


@pytest.fixture
def sample_phase3_input_office_rc(
    sample_building_graph_office_rc, sample_structural_design_graph
) -> Phase3Input:
    return Phase3Input(
        building_graph=sample_building_graph_office_rc,
        structural_design_graph=sample_structural_design_graph,
        location=LocationData(
            latitude=41.88,
            longitude=-87.63,
            city="Chicago",
            state_or_region="IL",
        ),
        material_family=MaterialFamily.REINFORCED_CONCRETE,
        risk_category=RiskCategory.II,
        exposure_category=ExposureCategory.B,
        basic_wind_speed_m_per_s=44.7,
        site_class="D",
        Ss=0.20,
        S1=0.09,
    )


@pytest.fixture
def sample_phase3_input_residential_steel(
    sample_building_graph_residential_steel,
    sample_structural_design_graph_residential,
) -> Phase3Input:
    return Phase3Input(
        building_graph=sample_building_graph_residential_steel,
        structural_design_graph=sample_structural_design_graph_residential,
        location=LocationData(
            latitude=34.05,
            longitude=-118.24,
            city="Los Angeles",
            state_or_region="CA",
        ),
        material_family=MaterialFamily.STRUCTURAL_STEEL,
        risk_category=RiskCategory.II,
        exposure_category=ExposureCategory.C,
        basic_wind_speed_m_per_s=38.0,
        site_class="D",
        Ss=1.5,
        S1=0.6,
    )


@pytest.fixture
def empty_builder() -> AssumptionBuilder:
    return AssumptionBuilder()
