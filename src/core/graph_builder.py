"""Building Graph orchestrator.

``GraphBuilder`` is the single entry point that accepts any input channel's
data and assembles a fully validated ``BuildingGraph``.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

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
from src.schema.input_models import StructuredInputRequest
from src.utils.completeness_scorer import annotate_with_completeness
from src.utils.geometry import polygon_area_m2, polygon_perimeter_mm, rectangular_polygon_mm

from .grid_generator import GridGenerator
from .span_calculator import SpanCalculator
from .story_generator import StoryGenerator
from .zone_classifier import ZoneClassifier

logger = structlog.get_logger(__name__)


class GraphBuilder:
    """Orchestrates ``BuildingGraph`` construction from any input channel.

    *   ``from_structured_input`` — Channel A (form data)
    *   ``from_cad_data``         — Channel B (parsed CAD file)
    *   ``from_cv_output``        — Channel C (CV pipeline results)

    Each method validates the assembled graph before returning.
    """

    def __init__(self) -> None:
        self.grid_generator = GridGenerator()
        self.story_generator = StoryGenerator()
        self.span_calculator = SpanCalculator()
        self.zone_classifier = ZoneClassifier()

    # ------------------------------------------------------------------
    # Channel A — structured form input
    # ------------------------------------------------------------------

    def from_structured_input(self, request: StructuredInputRequest) -> BuildingGraph:
        """Build a complete ``BuildingGraph`` from user-supplied parameters."""
        t0 = time.perf_counter()
        assumptions: list[str] = []

        # 1. Grid
        grid = self.grid_generator.generate(
            length_mm=request.length_mm,
            width_mm=request.width_mm,
            preferred_bay_x_mm=request.preferred_bay_x_mm,
            preferred_bay_y_mm=request.preferred_bay_y_mm,
            min_bay_mm=request.min_bay_mm,
            max_bay_mm=request.max_bay_mm,
            x_constraints=request.x_constraints,
            y_constraints=request.y_constraints,
        )
        assumptions.append("Generated regular structural grid from preferred bay sizes")

        # 2. Floor area
        floor_area_m2 = (request.length_mm * request.width_mm) / 1_000_000

        # 3. Stories
        stories = self.story_generator.generate(
            num_stories=request.num_stories,
            floor_to_floor_mm=request.floor_to_floor_mm,
            ground_floor_height_mm=request.ground_floor_height_mm,
            roof_type=request.roof_type.value,
            occupancy_type=request.occupancy_type,
            occupancy_by_floor=request.occupancy_by_floor,
            floor_area_m2=floor_area_m2,
        )
        total_height = sum(s.floor_to_floor_mm for s in stories)

        # 4. Perimeter walls
        story_ids = [s.id for s in stories]
        walls = self._generate_perimeter_walls(
            request.length_mm,
            request.width_mm,
            story_ids,
            request.material_preference,
        )
        assumptions.append("Perimeter walls generated as facade type around building footprint")

        # 5. Facade
        facade = self._compute_facade(request.length_mm, request.width_mm)

        # 6. Default room — one open-plan room per floor
        rooms = self._generate_default_rooms(
            request.length_mm, request.width_mm, stories, request.occupancy_type
        )
        assumptions.append("Each floor treated as single open-plan zone")

        # 7. Column candidates (wall-type aware — Gap 6)
        column_candidates = self.zone_classifier.identify_columns(grid, walls=walls)

        # 8. Cores from user placements (if any)
        cores = self._cores_from_placements(request, story_ids)

        # 9. Assemble project info
        project = ProjectInfo(
            name=request.project_name,
            location=request.location,
            occupancy_type=request.occupancy_type,
            material_preference=request.material_preference,
            num_stories=request.num_stories,
            total_height_mm=total_height,
            building_code=request.building_code,
        )

        elapsed = round(time.perf_counter() - t0, 4)

        metadata = BuildingMetadata(
            input_source=InputSource.STRUCTURED_FORM,
            confidence_scores=ConfidenceScores(overall=1.0),
            assumptions_made=assumptions,
            warnings=[],
            processing_time_seconds=elapsed,
        )

        graph = BuildingGraph(
            project=project,
            stories=stories,
            grid=grid,
            walls=walls,
            rooms=rooms,
            openings=[],
            column_candidates=column_candidates,
            cores=cores,
            facade=facade,
            metadata=metadata,
        )

        annotate_with_completeness(graph)

        logger.info(
            "building_graph_built",
            source="structured_input",
            stories=len(stories),
            walls=len(walls),
            columns=len(column_candidates),
            elapsed_s=elapsed,
            completeness=graph.metadata.confidence_scores.overall,
        )
        return graph

    # ------------------------------------------------------------------
    # Channel B — CAD data (stub — implemented in Step 4)
    # ------------------------------------------------------------------

    def from_cad_data(
        self,
        parsed_data: dict[str, Any],
        project_name: str = "CAD Import",
        occupancy_type: OccupancyType = OccupancyType.OFFICE,
        material_preference: MaterialPreference = MaterialPreference.REINFORCED_CONCRETE,
        num_stories: int = 1,
        floor_to_floor_mm: float = 3900,
    ) -> BuildingGraph:
        """Map parsed CAD entities to a Building Graph.

        *parsed_data* is the dict returned by ``DXFParser.parse()`` or
        ``IFCParser.parse()``.
        """
        t0 = time.perf_counter()
        assumptions: list[str] = []
        warnings: list[str] = []

        # --- Grid ---
        raw_grid = parsed_data.get("grid_lines", {"x_lines": [], "y_lines": []})
        x_lines_raw = raw_grid.get("x_lines", [])
        y_lines_raw = raw_grid.get("y_lines", [])

        from src.parsers.grid_extractor import GridExtractor
        from src.parsers.wall_extractor import WallExtractor
        from src.parsers.room_extractor import RoomExtractor

        text_annotations = parsed_data.get("text_annotations", [])
        grid_ext = GridExtractor()
        grid_data = grid_ext.extract(raw_grid, text_annotations)

        x_gl = grid_data["x_lines"]
        y_gl = grid_data["y_lines"]

        if len(x_gl) < 2 or len(y_gl) < 2:
            # Fall back to inferring grid from walls
            wall_ext = WallExtractor()
            clean_walls = wall_ext.extract(parsed_data.get("walls", []))
            if clean_walls:
                xs = sorted({w["start"][0] for w in clean_walls} | {w["end"][0] for w in clean_walls})
                ys = sorted({w["start"][1] for w in clean_walls} | {w["end"][1] for w in clean_walls})
                if len(xs) >= 2:
                    x_gl = [GridLine(id=chr(65 + i), position_mm=x) for i, x in enumerate(xs[:26])]
                if len(ys) >= 2:
                    y_gl = [GridLine(id=str(i + 1), position_mm=y) for i, y in enumerate(ys)]
                assumptions.append("Grid inferred from wall endpoints (no grid layer in CAD)")
            else:
                warnings.append("No grid lines or walls found in CAD file")
                x_gl = [GridLine(id="A", position_mm=0), GridLine(id="B", position_mm=10000)]
                y_gl = [GridLine(id="1", position_mm=0), GridLine(id="2", position_mm=10000)]

        # Single wall / collinear walls can yield <2 unique X or Y samples — still degenerate.
        if len(x_gl) < 2 or len(y_gl) < 2:
            warnings.append("Degenerate grid after wall inference; using placeholder extents")
            x_gl = [GridLine(id="A", position_mm=0), GridLine(id="B", position_mm=10000)]
            y_gl = [GridLine(id="1", position_mm=0), GridLine(id="2", position_mm=10000)]

        bays = self._build_bays_from_lines(x_gl, y_gl)
        grid = GridSystem(x_lines=x_gl, y_lines=y_gl, bays=bays)

        # --- Walls ---
        wall_ext = WallExtractor()
        clean_walls = wall_ext.extract(parsed_data.get("walls", []))
        story_ids = [f"story-{i}" for i in range(num_stories)]

        wall_segments = [
            WallSegment(
                id=f"wall-cad-{i}",
                type=WallType.STRUCTURAL,
                start=w["start"],
                end=w["end"],
                thickness_mm=w["thickness_mm"],
                stories=story_ids,
            )
            for i, w in enumerate(clean_walls)
        ]

        # --- Rooms ---
        room_ext = RoomExtractor()
        raw_rooms = parsed_data.get("rooms", [])
        room_dicts = room_ext.extract(raw_rooms, text_annotations, story_id="story-0")
        rooms = [
            Room(
                id=rd["id"],
                label=rd["label"],
                type=RoomType(rd["type"]),
                polygon=rd["polygon"],
                area_m2=rd["area_m2"],
                story=rd["story"],
                perimeter_mm=rd.get("perimeter_mm"),
            )
            for rd in room_dicts
        ]

        # --- Openings ---
        openings: list[Opening] = []
        for i, door in enumerate(parsed_data.get("doors", [])):
            width = door.get("width_mm", 900)
            openings.append(Opening(
                id=f"door-{i}",
                type=OpeningType.DOOR,
                wall_id=wall_segments[0].id if wall_segments else "unknown",
                position_mm=0,
                width_mm=width,
            ))
        for i, win in enumerate(parsed_data.get("windows", [])):
            width = win.get("width_mm", 1200)
            openings.append(Opening(
                id=f"window-{i}",
                type=OpeningType.WINDOW,
                wall_id=wall_segments[0].id if wall_segments else "unknown",
                position_mm=0,
                width_mm=width,
            ))

        # --- Stories ---
        length_mm = x_gl[-1].position_mm - x_gl[0].position_mm
        width_mm = y_gl[-1].position_mm - y_gl[0].position_mm
        floor_area = (length_mm * width_mm) / 1_000_000

        stories = self.story_generator.generate(
            num_stories=num_stories,
            floor_to_floor_mm=floor_to_floor_mm,
            occupancy_type=occupancy_type,
            floor_area_m2=floor_area,
        )
        total_height = sum(s.floor_to_floor_mm for s in stories)

        # --- Facade ---
        facade = self._compute_facade(length_mm, width_mm)

        # --- Columns --- (wall-type aware — Gap 6)
        column_candidates = self.zone_classifier.identify_columns(grid, walls=wall_segments)

        # Add any CAD-detected columns with higher confidence
        for col in parsed_data.get("columns", []):
            column_candidates.append(ColumnCandidate(
                position=col["position"],
                confidence=0.95,
                notes="Detected from CAD column layer",
            ))

        # --- Cores ---
        cores = self.zone_classifier.identify_cores(grid, rooms, wall_segments)

        # --- Project info ---
        project = ProjectInfo(
            name=project_name,
            location=Location(lat=0, lng=0),
            occupancy_type=occupancy_type,
            material_preference=material_preference,
            num_stories=num_stories,
            total_height_mm=total_height,
        )

        elapsed = round(time.perf_counter() - t0, 4)
        input_source = InputSource.DXF_FILE
        units_str = parsed_data.get("units", "mm")
        if units_str != "mm":
            assumptions.append(f"Converted from {units_str} to mm")

        metadata = BuildingMetadata(
            input_source=input_source,
            confidence_scores=ConfidenceScores(
                wall_detection=0.85,
                room_classification=0.7 if rooms else None,
                grid_detection=0.9 if len(x_gl) > 2 else 0.5,
                overall=0.8,
            ),
            assumptions_made=assumptions,
            warnings=warnings,
            processing_time_seconds=elapsed,
        )

        graph = BuildingGraph(
            project=project,
            stories=stories,
            grid=grid,
            walls=wall_segments,
            rooms=rooms if rooms else self._generate_default_rooms(length_mm, width_mm, stories, occupancy_type),
            openings=openings,
            column_candidates=column_candidates,
            cores=cores,
            facade=facade,
            metadata=metadata,
        )

        annotate_with_completeness(graph)

        logger.info(
            "building_graph_built",
            source="cad_data",
            walls=len(wall_segments),
            rooms=len(rooms),
            elapsed_s=elapsed,
            completeness=graph.metadata.confidence_scores.overall,
        )
        return graph

    # ------------------------------------------------------------------
    # Channel C — CV pipeline output (stub — implemented in Step 9)
    # ------------------------------------------------------------------

    def from_cv_output(self, cv_results: dict[str, Any]) -> BuildingGraph:
        """Map CV pipeline results to a Building Graph.

        *cv_results* contains keys like ``walls``, ``rooms``, ``grid``,
        ``symbols``, ``dimensions``, ``text_labels``.
        Implementation details in Steps 6–9.
        """
        raise NotImplementedError("CV output → BuildingGraph mapping is in Step 9")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_perimeter_walls(
        length_mm: float,
        width_mm: float,
        story_ids: list[str],
        material: MaterialPreference,
        thickness_mm: float = 200,
    ) -> list[WallSegment]:
        """Create four perimeter (facade) walls."""
        mat = material.value
        return [
            WallSegment(
                id="wall-S",
                type=WallType.FACADE,
                start=[0, 0],
                end=[length_mm, 0],
                thickness_mm=thickness_mm,
                stories=story_ids,
                material=mat,
            ),
            WallSegment(
                id="wall-E",
                type=WallType.FACADE,
                start=[length_mm, 0],
                end=[length_mm, width_mm],
                thickness_mm=thickness_mm,
                stories=story_ids,
                material=mat,
            ),
            WallSegment(
                id="wall-N",
                type=WallType.FACADE,
                start=[length_mm, width_mm],
                end=[0, width_mm],
                thickness_mm=thickness_mm,
                stories=story_ids,
                material=mat,
            ),
            WallSegment(
                id="wall-W",
                type=WallType.FACADE,
                start=[0, width_mm],
                end=[0, 0],
                thickness_mm=thickness_mm,
                stories=story_ids,
                material=mat,
            ),
        ]

    @staticmethod
    def _compute_facade(length_mm: float, width_mm: float) -> Facade:
        perimeter_polygon = rectangular_polygon_mm(0, 0, length_mm, width_mm)
        perimeter_length = 2 * (length_mm + width_mm)
        return Facade(
            perimeter_polygon=perimeter_polygon,
            perimeter_length_mm=perimeter_length,
        )

    @staticmethod
    def _generate_default_rooms(
        length_mm: float,
        width_mm: float,
        stories: list[Story],
        occupancy: OccupancyType,
    ) -> list[Room]:
        """One open-plan room per storey covering the full footprint."""
        rooms: list[Room] = []
        polygon = rectangular_polygon_mm(0, 0, length_mm, width_mm)
        area = polygon_area_m2(polygon)
        perimeter = polygon_perimeter_mm(polygon)

        # Map occupancy to a reasonable room type
        type_map: dict[OccupancyType, RoomType] = {
            OccupancyType.OFFICE: RoomType.OFFICE,
            OccupancyType.RESIDENTIAL: RoomType.LIVING_ROOM,
            OccupancyType.RETAIL: RoomType.LOBBY,
            OccupancyType.HOSPITALITY: RoomType.LOBBY,
        }
        default_type = type_map.get(occupancy, RoomType.UNDEFINED)

        for story in stories:
            rooms.append(
                Room(
                    id=f"room-{story.id}",
                    label=story.usage,
                    type=default_type,
                    polygon=polygon,
                    area_m2=round(area, 2),
                    story=story.id,
                    perimeter_mm=round(perimeter, 2),
                )
            )
        return rooms

    @staticmethod
    def _build_bays_from_lines(
        x_lines: list[GridLine], y_lines: list[GridLine]
    ) -> list[Bay]:
        """Build bay objects from pre-existing grid lines."""
        bays: list[Bay] = []
        for i in range(len(x_lines) - 1):
            for j in range(len(y_lines) - 1):
                bays.append(
                    Bay(
                        id=f"bay-{x_lines[i].id}-{y_lines[j].id}",
                        span_x_mm=round(x_lines[i + 1].position_mm - x_lines[i].position_mm, 2),
                        span_y_mm=round(y_lines[j + 1].position_mm - y_lines[j].position_mm, 2),
                        grid_x_start=x_lines[i].id,
                        grid_x_end=x_lines[i + 1].id,
                        grid_y_start=y_lines[j].id,
                        grid_y_end=y_lines[j + 1].id,
                    )
                )
        return bays

    @staticmethod
    def _cores_from_placements(
        request: StructuredInputRequest,
        story_ids: list[str],
    ) -> list[Core]:
        """Convert user-specified core placements to ``Core`` objects."""
        cores: list[Core] = []
        for i, cp in enumerate(request.core_placements):
            polygon = rectangular_polygon_mm(
                cp.x_start_mm, cp.y_start_mm, cp.x_end_mm, cp.y_end_mm
            )
            if cp.contains_elevator and cp.contains_stairs:
                ct = CoreType.ELEVATOR_STAIR
            elif cp.contains_elevator:
                ct = CoreType.ELEVATOR_ONLY
            elif cp.contains_stairs:
                ct = CoreType.STAIR_ONLY
            else:
                ct = CoreType.SERVICE

            cores.append(
                Core(
                    id=f"core-{i + 1}",
                    type=ct,
                    polygon=polygon,
                    contains_elevator=cp.contains_elevator,
                    contains_stairs=cp.contains_stairs,
                    stories=story_ids,
                )
            )
        return cores
