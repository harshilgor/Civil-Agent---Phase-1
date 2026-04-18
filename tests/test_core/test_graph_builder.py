"""Tests for GraphBuilder — the main orchestrator."""

from __future__ import annotations

import pytest

from src.core.graph_builder import GraphBuilder
from src.schema.building_graph import BuildingGraph
from src.schema.enums import (
    InputSource,
    MaterialPreference,
    OccupancyType,
    WallType,
)
from src.schema.input_models import CorePlacement, StructuredInputRequest
from src.schema.building_graph import Location


@pytest.fixture()
def builder() -> GraphBuilder:
    return GraphBuilder()


@pytest.fixture()
def basic_request() -> StructuredInputRequest:
    return StructuredInputRequest(
        project_name="Test Tower",
        location=Location(lat=37.77, lng=-122.42, city="San Francisco"),
        length_mm=32000,
        width_mm=24000,
        num_stories=5,
        floor_to_floor_mm=3600,
        ground_floor_height_mm=4500,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        preferred_bay_x_mm=8000,
        preferred_bay_y_mm=8000,
    )


class TestFromStructuredInput:
    def test_returns_valid_building_graph(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert isinstance(bg, BuildingGraph)

    def test_project_info_matches(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert bg.project.name == "Test Tower"
        assert bg.project.num_stories == 5
        assert bg.project.occupancy_type == OccupancyType.OFFICE

    def test_stories_count(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert len(bg.stories) == 5

    def test_total_height(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        expected = 4500 + 4 * 3600  # ground + 4 typical
        assert bg.project.total_height_mm == expected

    def test_four_perimeter_walls(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert len(bg.walls) == 4
        for w in bg.walls:
            assert w.type == WallType.FACADE

    def test_facade_perimeter(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        expected_perimeter = 2 * (32000 + 24000)
        assert bg.facade.perimeter_length_mm == expected_perimeter

    def test_grid_generated(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert len(bg.grid.x_lines) >= 2
        assert len(bg.grid.y_lines) >= 2
        assert len(bg.grid.bays) > 0

    def test_column_candidates_at_intersections(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        n_x = len(bg.grid.x_lines)
        n_y = len(bg.grid.y_lines)
        assert len(bg.column_candidates) == n_x * n_y

    def test_corner_columns_required(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        required = [c for c in bg.column_candidates if c.is_required]
        assert len(required) == 4  # four corners

    def test_rooms_one_per_story(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert len(bg.rooms) == 5

    def test_metadata_source(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        assert bg.metadata.input_source == InputSource.STRUCTURED_FORM
        assert bg.metadata.confidence_scores.overall >= 0.85
        assert len(bg.metadata.assumptions_made) > 0

    def test_serialization_roundtrip(
        self, builder: GraphBuilder, basic_request: StructuredInputRequest
    ):
        bg = builder.from_structured_input(basic_request)
        json_str = bg.model_dump_json()
        restored = BuildingGraph.model_validate_json(json_str)
        assert restored.project.name == bg.project.name
        assert len(restored.stories) == len(bg.stories)


class TestWithCorePlacements:
    def test_core_from_placement(self, builder: GraphBuilder):
        req = StructuredInputRequest(
            project_name="With Core",
            location=Location(lat=0, lng=0),
            length_mm=20000,
            width_mm=20000,
            num_stories=3,
            core_placements=[
                CorePlacement(
                    x_start_mm=8000, y_start_mm=8000,
                    x_end_mm=12000, y_end_mm=12000,
                    contains_elevator=True, contains_stairs=True,
                ),
            ],
        )
        bg = builder.from_structured_input(req)
        assert len(bg.cores) == 1
        assert bg.cores[0].contains_elevator
        assert bg.cores[0].contains_stairs


class TestWithConstraints:
    def test_grid_respects_x_constraint(self, builder: GraphBuilder):
        req = StructuredInputRequest(
            project_name="Constrained",
            location=Location(lat=0, lng=0),
            length_mm=32000,
            width_mm=16000,
            num_stories=1,
            x_constraints=[12000],
        )
        bg = builder.from_structured_input(req)
        x_positions = {gl.position_mm for gl in bg.grid.x_lines}
        assert 12000 in x_positions


class TestFromCADData:
    def test_from_cad_data_with_empty_dict(self, builder: GraphBuilder):
        bg = builder.from_cad_data({})
        assert bg.project.num_stories == 1
        assert len(bg.grid.x_lines) >= 2

    def test_from_cv_output_not_implemented(self, builder: GraphBuilder):
        with pytest.raises(NotImplementedError):
            builder.from_cv_output({})
