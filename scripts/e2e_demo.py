"""End-to-end demo: structured input → BuildingGraph → NetworkX → JSON."""

from src.core.graph_builder import GraphBuilder
from src.schema.input_models import StructuredInputRequest
from src.schema.building_graph import BuildingGraph, Location
from src.schema.enums import OccupancyType, MaterialPreference
from src.graph.spatial_graph import SpatialBuildingGraph


def main():
    req = StructuredInputRequest(
        project_name="8-Story Office Tower",
        location=Location(
            lat=37.77, lng=-122.42, city="San Francisco",
            state="CA", country="US", seismic_zone="D",
        ),
        length_mm=40000, width_mm=25000, num_stories=8,
        floor_to_floor_mm=3600, ground_floor_height_mm=4500,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        preferred_bay_x_mm=8000, preferred_bay_y_mm=8000,
    )

    builder = GraphBuilder()
    bg = builder.from_structured_input(req)

    print(f"Project: {bg.project.name}")
    print(f"Stories: {len(bg.stories)}")
    print(f"Total height: {bg.project.total_height_mm} mm")
    x = len(bg.grid.x_lines)
    y = len(bg.grid.y_lines)
    print(f"Grid: {x}x x {y}y = {len(bg.grid.bays)} bays")
    print(f"Walls: {len(bg.walls)}")
    print(f"Rooms: {len(bg.rooms)}")
    req_cols = sum(1 for c in bg.column_candidates if c.is_required)
    print(f"Columns: {len(bg.column_candidates)} ({req_cols} required)")
    print(f"Facade perimeter: {bg.facade.perimeter_length_mm} mm")
    print(f"Source: {bg.metadata.input_source.value}")
    print(f"Assumptions: {bg.metadata.assumptions_made}")
    print(f"Processing: {bg.metadata.processing_time_seconds}s")

    sbg = SpatialBuildingGraph.from_building_graph(bg)
    info = sbg.get_connectivity_info()
    print(f"Graph: {info['nodes']} nodes, {info['edges']} edges, connected={info['is_connected']}")

    j = bg.model_dump_json()
    print(f"JSON size: {len(j)} bytes")
    restored = BuildingGraph.model_validate_json(j)
    assert restored.project.name == bg.project.name
    print("JSON roundtrip: OK")


if __name__ == "__main__":
    main()
