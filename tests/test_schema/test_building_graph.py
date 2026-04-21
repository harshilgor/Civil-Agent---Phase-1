"""Tests for the Building Graph schema and all sub-models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema.building_graph import (
    Bay,
    BuildingGraph,
    BuildingMetadata,
    ColumnCandidate,
    ConfidenceScores,
    Core,
    Facade,
    GridLine,
    GridSystem,
    Location,
    Opening,
    ProjectInfo,
    Room,
    Story,
    WallSegment,
)
from src.schema.enums import (
    CoreType,
    InputSource,
    MaterialPreference,
    OccupancyType,
    OpeningType,
    RoomType,
    WallType,
)


# ── Location ──────────────────────────────────────────────────────────────

class TestLocation:
    def test_valid(self):
        loc = Location(lat=40.7128, lng=-74.0060, city="New York")
        assert loc.lat == 40.7128
        assert loc.city == "New York"

    def test_lat_out_of_range(self):
        with pytest.raises(ValidationError, match="lat"):
            Location(lat=91, lng=0)

    def test_lng_out_of_range(self):
        with pytest.raises(ValidationError, match="lng"):
            Location(lat=0, lng=181)

    def test_minimal_fields(self):
        loc = Location(lat=0, lng=0)
        assert loc.city is None
        assert loc.seismic_zone is None


# ── ProjectInfo ───────────────────────────────────────────────────────────

class TestProjectInfo:
    def test_valid(self, sample_location):
        pi = ProjectInfo(
            name="Tower A",
            location=sample_location,
            occupancy_type=OccupancyType.OFFICE,
            material_preference=MaterialPreference.STRUCTURAL_STEEL,
            num_stories=10,
            total_height_mm=39000,
        )
        assert pi.num_stories == 10
        assert pi.building_code == "IBC 2021"

    def test_zero_stories_rejected(self, sample_location):
        with pytest.raises(ValidationError, match="num_stories"):
            ProjectInfo(
                name="X",
                location=sample_location,
                occupancy_type=OccupancyType.OFFICE,
                material_preference=MaterialPreference.REINFORCED_CONCRETE,
                num_stories=0,
                total_height_mm=1000,
            )

    def test_stories_above_200_rejected(self, sample_location):
        with pytest.raises(ValidationError, match="num_stories"):
            ProjectInfo(
                name="X",
                location=sample_location,
                occupancy_type=OccupancyType.OFFICE,
                material_preference=MaterialPreference.REINFORCED_CONCRETE,
                num_stories=201,
                total_height_mm=500000,
            )

    def test_empty_name_rejected(self, sample_location):
        with pytest.raises(ValidationError, match="name"):
            ProjectInfo(
                name="",
                location=sample_location,
                occupancy_type=OccupancyType.OFFICE,
                material_preference=MaterialPreference.REINFORCED_CONCRETE,
                num_stories=1,
                total_height_mm=3900,
            )


# ── Story ─────────────────────────────────────────────────────────────────

class TestStory:
    def test_valid(self):
        s = Story(
            id="s1", level=0, floor_to_floor_mm=3900,
            elevation_mm=0, floor_area_gross_m2=500, usage="OFFICE",
        )
        assert s.floor_to_floor_mm == 3900

    def test_floor_height_too_low(self):
        with pytest.raises(ValidationError, match="floor_to_floor_mm"):
            Story(
                id="s1", level=0, floor_to_floor_mm=2000,
                elevation_mm=0, floor_area_gross_m2=500, usage="OFFICE",
            )

    def test_floor_height_too_high(self):
        with pytest.raises(ValidationError, match="floor_to_floor_mm"):
            Story(
                id="s1", level=0, floor_to_floor_mm=25000,
                elevation_mm=0, floor_area_gross_m2=500, usage="OFFICE",
            )


# ── GridSystem ────────────────────────────────────────────────────────────

class TestGridSystem:
    def test_valid(self, sample_grid):
        assert len(sample_grid.x_lines) == 5
        assert len(sample_grid.y_lines) == 4
        assert len(sample_grid.bays) == 12

    def test_non_ascending_x_lines_rejected(self):
        with pytest.raises(ValidationError, match="ascending"):
            GridSystem(
                x_lines=[
                    GridLine(id="A", position_mm=8000),
                    GridLine(id="B", position_mm=0),
                ],
                y_lines=[GridLine(id="1", position_mm=0)],
                bays=[],
            )

    def test_duplicate_positions_rejected(self):
        with pytest.raises(ValidationError, match="ascending"):
            GridSystem(
                x_lines=[
                    GridLine(id="A", position_mm=0),
                    GridLine(id="B", position_mm=0),
                ],
                y_lines=[GridLine(id="1", position_mm=0)],
                bays=[],
            )

    def test_bay_span_must_be_positive(self):
        with pytest.raises(ValidationError, match="span_x_mm"):
            Bay(
                id="b1", span_x_mm=0, span_y_mm=8000,
                grid_x_start="A", grid_x_end="B",
                grid_y_start="1", grid_y_end="2",
            )


# ── WallSegment ───────────────────────────────────────────────────────────

class TestWallSegment:
    def test_valid(self):
        w = WallSegment(
            id="w1", type=WallType.STRUCTURAL,
            start=[0, 0], end=[8000, 0],
            thickness_mm=300, stories=["s0"],
        )
        assert w.thickness_mm == 300

    def test_zero_thickness_rejected(self):
        with pytest.raises(ValidationError, match="thickness_mm"):
            WallSegment(
                id="w1", type=WallType.STRUCTURAL,
                start=[0, 0], end=[8000, 0],
                thickness_mm=0, stories=["s0"],
            )

    def test_empty_stories_rejected(self):
        with pytest.raises(ValidationError, match="stories"):
            WallSegment(
                id="w1", type=WallType.STRUCTURAL,
                start=[0, 0], end=[8000, 0],
                thickness_mm=200, stories=[],
            )

    def test_start_end_must_be_length_2(self):
        with pytest.raises(ValidationError):
            WallSegment(
                id="w1", type=WallType.STRUCTURAL,
                start=[0, 0, 0], end=[8000, 0],
                thickness_mm=200, stories=["s0"],
            )


# ── Room ──────────────────────────────────────────────────────────────────

class TestRoom:
    def test_valid(self):
        r = Room(
            id="r1", label="Office A", type=RoomType.OFFICE,
            polygon=[[0, 0], [8000, 0], [8000, 8000], [0, 8000], [0, 0]],
            area_m2=64.0, story="s0",
        )
        assert r.area_m2 == 64.0

    def test_polygon_too_few_points(self):
        with pytest.raises(ValidationError, match="at least 3"):
            Room(
                id="r1", label="X", type=RoomType.UNDEFINED,
                polygon=[[0, 0], [1000, 0]],
                area_m2=0, story="s0",
            )

    def test_polygon_bad_point_shape(self):
        with pytest.raises(ValidationError, match="\\[x, y\\]"):
            Room(
                id="r1", label="X", type=RoomType.UNDEFINED,
                polygon=[[0, 0, 0], [1, 2, 3], [4, 5, 6]],
                area_m2=0, story="s0",
            )


# ── Opening ───────────────────────────────────────────────────────────────

class TestOpening:
    def test_valid(self):
        o = Opening(
            id="o1", type=OpeningType.DOOR,
            wall_id="w1", position_mm=2000, width_mm=900,
        )
        assert o.width_mm == 900

    def test_negative_position_rejected(self):
        with pytest.raises(ValidationError, match="position_mm"):
            Opening(
                id="o1", type=OpeningType.WINDOW,
                wall_id="w1", position_mm=-100, width_mm=1200,
            )


# ── ColumnCandidate ───────────────────────────────────────────────────────

class TestColumnCandidate:
    def test_valid(self):
        c = ColumnCandidate(position=[0, 0], confidence=0.85)
        assert c.confidence == 0.85

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError, match="confidence"):
            ColumnCandidate(position=[0, 0], confidence=1.5)

    def test_confidence_negative(self):
        with pytest.raises(ValidationError, match="confidence"):
            ColumnCandidate(position=[0, 0], confidence=-0.1)


# ── Core ──────────────────────────────────────────────────────────────────

class TestCore:
    def test_valid(self):
        c = Core(
            id="c1", type=CoreType.ELEVATOR_STAIR,
            polygon=[[0, 0], [3000, 0], [3000, 5000], [0, 5000]],
            contains_elevator=True, contains_stairs=True,
        )
        assert c.contains_elevator

    def test_polygon_too_few_points(self):
        with pytest.raises(ValidationError, match="at least 3"):
            Core(id="c1", type=CoreType.MEP, polygon=[[0, 0], [1, 1]])


# ── Facade ────────────────────────────────────────────────────────────────

class TestFacade:
    def test_valid(self, sample_facade):
        assert sample_facade.perimeter_length_mm == 112000

    def test_polygon_too_few_points(self):
        with pytest.raises(ValidationError, match="at least 3"):
            Facade(perimeter_polygon=[[0, 0], [1, 1]], perimeter_length_mm=100)


# ── ConfidenceScores ──────────────────────────────────────────────────────

class TestConfidenceScores:
    def test_all_none_by_default(self):
        cs = ConfidenceScores()
        assert cs.wall_detection is None
        assert cs.overall is None

    def test_out_of_range(self):
        with pytest.raises(ValidationError, match="overall"):
            ConfidenceScores(overall=2.0)


# ── BuildingGraph ─────────────────────────────────────────────────────────

class TestBuildingGraph:
    def test_valid_graph(self, sample_building_graph):
        bg = sample_building_graph
        assert bg.project.name == "Test Office Tower"
        assert len(bg.stories) == 3
        assert len(bg.grid.x_lines) == 5

    def test_story_count_mismatch_rejected(
        self, sample_project_info, sample_stories, sample_grid,
        sample_walls, sample_rooms, sample_facade,
        sample_column_candidates, sample_metadata,
    ):
        bad_stories = sample_stories[:2]  # only 2, project says 3
        with pytest.raises(ValidationError, match="does not match"):
            BuildingGraph(
                project=sample_project_info,
                stories=bad_stories,
                grid=sample_grid,
                walls=sample_walls,
                rooms=sample_rooms,
                column_candidates=sample_column_candidates,
                facade=sample_facade,
                metadata=sample_metadata,
            )

    def test_serialization_roundtrip(self, sample_building_graph):
        json_str = sample_building_graph.model_dump_json()
        restored = BuildingGraph.model_validate_json(json_str)
        assert restored.project.name == sample_building_graph.project.name
        assert len(restored.stories) == len(sample_building_graph.stories)
        assert len(restored.grid.bays) == len(sample_building_graph.grid.bays)

    def test_empty_stories_rejected(
        self, sample_project_info, sample_grid, sample_walls,
        sample_rooms, sample_facade, sample_column_candidates, sample_metadata,
    ):
        sample_project_info_1 = sample_project_info.model_copy(update={"num_stories": 1})
        with pytest.raises(ValidationError):
            BuildingGraph(
                project=sample_project_info_1,
                stories=[],
                grid=sample_grid,
                walls=sample_walls,
                rooms=sample_rooms,
                column_candidates=sample_column_candidates,
                facade=sample_facade,
                metadata=sample_metadata,
            )


# ── Enum coverage ─────────────────────────────────────────────────────────

class TestEnums:
    def test_occupancy_values(self):
        assert OccupancyType.OFFICE.value == "OFFICE"
        assert len(OccupancyType) == 9

    def test_material_values(self):
        assert MaterialPreference.COMPOSITE.value == "COMPOSITE"
        assert len(MaterialPreference) == 5

    def test_wall_type_values(self):
        assert WallType.SHEAR_WALL.value == "SHEAR_WALL"
        assert len(WallType) == 5

    def test_room_type_values(self):
        assert RoomType.UNDEFINED.value == "UNDEFINED"
        assert len(RoomType) == 14

    def test_input_source_values(self):
        assert InputSource.FLOOR_PLAN_IMAGE.value == "FLOOR_PLAN_IMAGE"
        assert len(InputSource) == 5
