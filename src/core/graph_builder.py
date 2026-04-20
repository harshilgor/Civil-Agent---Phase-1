"""Building Graph orchestrator.

``GraphBuilder`` is the single entry point that accepts any input channel's
data and assembles a fully validated ``BuildingGraph``.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

import structlog

from src.schema.building_graph import (
    Bay,
    BuildingGraph,
    BuildingMetadata,
    ConfidenceScores,
    Core,
    Facade,
    GridLine,
    GridSystem,
    ProjectInfo,
    Room,
    Story,
    WallSegment,
)
from src.schema.enums import (
    BuildingType,
    CoreType,
    InputSource,
    MaterialPreference,
    OccupancyType,
    RoomType,
    WallType,
)
from src.schema.input_models import StructuredInputRequest
from src.schema.provenance import ProvenanceRecord
from src.utils.completeness_scorer import annotate_with_completeness
from src.utils.geometry import polygon_area_m2, polygon_perimeter_mm, rectangular_polygon_mm

from .assumption_builder import (
    _DEFAULT_WALL_THICKNESS_MM,
    StructuredInputAssumptionBuilder,
)
from .grid_generator import GridGenerator
from .provenance_helpers import structured_form_provenance
from .span_calculator import SpanCalculator
from .story_generator import StoryGenerator
from .zone_classifier import ZoneClassifier


# ---------------------------------------------------------------------------
# Channel A helper: occupancy -> coarse BuildingType enum.
#
# ``BuildingType`` is the high-level physical family the VLM gap-filler would
# emit from a CAD / image input; for Channel A we don't have perception at
# all, so we derive it heuristically from the user-supplied ``OccupancyType``
# program label.  This is exposed on ``metadata.inferred_building_type`` so
# the Phase-3 load combinator treats Channel A graphs uniformly with the
# other channels (it can special-case residential vs commercial without
# having to branch on input_source).
# ---------------------------------------------------------------------------

_OCCUPANCY_TO_BUILDING_TYPE: dict[OccupancyType, BuildingType] = {
    OccupancyType.OFFICE: BuildingType.COMMERCIAL,
    OccupancyType.RETAIL: BuildingType.COMMERCIAL,
    OccupancyType.HOSPITALITY: BuildingType.COMMERCIAL,
    OccupancyType.RESIDENTIAL: BuildingType.RESIDENTIAL,
    OccupancyType.INDUSTRIAL: BuildingType.INDUSTRIAL,
    OccupancyType.EDUCATIONAL: BuildingType.INSTITUTIONAL,
    OccupancyType.HEALTHCARE: BuildingType.INSTITUTIONAL,
    OccupancyType.MIXED_USE: BuildingType.MIXED_USE,
    OccupancyType.PARKING: BuildingType.COMMERCIAL,
}

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

    def from_structured_input(
        self,
        request: StructuredInputRequest,
        *,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> BuildingGraph:
        """Build a complete ``BuildingGraph`` from user-supplied parameters.

        Args:
            request: Validated structured-form payload.
            run_id: Stable identifier of the current pipeline run, stamped on
                every emitted element's :class:`ProvenanceRecord`.  Defaults
                to ``job_id`` (or a freshly-minted uuid hex when neither is
                supplied) so the provenance chain is always populated.
            job_id: Persisted on ``metadata.job_id`` so the
                ``GET /api/v1/jobs/{job_id}`` endpoint can look this graph
                up.  Defaults to ``run_id`` when omitted.
        """
        t0 = time.perf_counter()
        run_id = run_id or job_id or uuid.uuid4().hex
        job_id = job_id or run_id

        provenance = structured_form_provenance(run_id=run_id)
        assumption_builder = StructuredInputAssumptionBuilder()
        assumption_builder.record_all_request_defaults(request)

        # Legacy free-form strings kept populated for backward compatibility
        # with older consumers; the structured register is the canonical
        # source going forward.
        assumptions_legacy: list[str] = []

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
        assumptions_legacy.append("Generated regular structural grid from preferred bay sizes")

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

        # 4. Perimeter walls (provenance-stamped)
        story_ids = [s.id for s in stories]
        walls = self._generate_perimeter_walls(
            request.length_mm,
            request.width_mm,
            story_ids,
            request.material_preference,
            provenance=provenance,
        )
        assumption_builder.record_perimeter_wall_thickness(
            _DEFAULT_WALL_THICKNESS_MM, is_default=True
        )
        assumption_builder.record_perimeter_wall_type(WallType.FACADE.value)
        assumptions_legacy.append("Perimeter walls generated as facade type around building footprint")

        # 5. Facade
        facade = self._compute_facade(request.length_mm, request.width_mm)

        # 6. Default rooms — provenance-stamped
        rooms = self._generate_default_rooms(
            request.length_mm,
            request.width_mm,
            stories,
            request.occupancy_type,
            provenance=provenance,
        )
        assumption_builder.record_single_room_per_floor(request.num_stories)
        assumptions_legacy.append("Each floor treated as single open-plan zone")

        # 7. Column candidates (wall-type aware — Gap 6)
        column_candidates = self.zone_classifier.identify_columns(grid, walls=walls)
        for c in column_candidates:
            c.provenance = provenance

        # 8. Cores from user placements (if any)
        cores = self._cores_from_placements(request, story_ids, provenance=provenance)

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

        # Channel A is user-verified input with no ML inference, so every
        # subsystem that *ran* scores a perfect 1.0.  ``opening_detection``
        # is left ``None`` (not 0.0 or 1.0) because Channel A never
        # enumerates doors or windows — the completeness scorer treats
        # ``None`` as "subsystem did not participate" rather than "ran and
        # failed".  The scorer then records ``SYMBOL_DETECTOR`` in the
        # ``missing_subsystems`` list of ``metadata.completeness``.
        confidence_scores = ConfidenceScores(
            wall_detection=1.0,
            room_classification=1.0,
            grid_detection=1.0,
            dimension_extraction=1.0,
            opening_detection=None,
            column_inference=1.0,
            overall=1.0,
        )

        metadata = BuildingMetadata(
            job_id=job_id,
            input_source=InputSource.STRUCTURED_FORM,
            inferred_building_type=_OCCUPANCY_TO_BUILDING_TYPE.get(
                request.occupancy_type, BuildingType.UNKNOWN
            ),
            confidence_scores=confidence_scores,
            assumptions_made=assumptions_legacy,
            assumption_register=assumption_builder.records,
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
            run_id=run_id,
            job_id=job_id,
            stories=len(stories),
            walls=len(walls),
            columns=len(column_candidates),
            assumptions=len(graph.metadata.assumption_register),
            elapsed_s=elapsed,
            completeness=graph.metadata.confidence_scores.overall,
        )
        return graph

    # ------------------------------------------------------------------
    # Channel B — CAD data (implemented in Step 6 via CadGraphBuilder)
    # ------------------------------------------------------------------

    def from_cad_data(
        self,
        parsed_data: dict[str, Any],
        project_name: str = "CAD Import",
        occupancy_type: OccupancyType = OccupancyType.OFFICE,
        material_preference: MaterialPreference = MaterialPreference.REINFORCED_CONCRETE,
        num_stories: int = 1,
        floor_to_floor_mm: float = 3900,
        *,
        input_source: Optional[InputSource] = None,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> BuildingGraph:
        """Map parsed CAD entities to a Building Graph.

        Delegates to :class:`src.core.cad_graph_builder.CadGraphBuilder` so
        legacy callers (pre-Step 6 tests, benchmarking scripts) continue
        to work while the production code path (the Celery worker in
        :mod:`src.worker.tasks`) imports ``CadGraphBuilder`` directly for
        the richer keyword surface.

        *parsed_data* is the dict returned by ``DXFParser.parse()`` or
        ``IFCParser.parse()``.
        """

        from .cad_graph_builder import CadGraphBuilder

        return CadGraphBuilder().build(
            parsed_data,
            input_source=input_source or InputSource.DXF_FILE,
            project_name=project_name,
            occupancy_type=occupancy_type,
            material_preference=material_preference,
            num_stories=num_stories,
            floor_to_floor_mm=floor_to_floor_mm,
            run_id=run_id,
            job_id=job_id,
        )

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
        *,
        provenance: Optional[ProvenanceRecord] = None,
    ) -> list[WallSegment]:
        """Create four perimeter (facade) walls."""
        mat = material.value
        common = {"thickness_mm": thickness_mm, "stories": story_ids, "material": mat}
        if provenance is not None:
            common["provenance"] = provenance
        return [
            WallSegment(id="wall-S", type=WallType.FACADE, start=[0, 0], end=[length_mm, 0], **common),
            WallSegment(
                id="wall-E", type=WallType.FACADE, start=[length_mm, 0], end=[length_mm, width_mm], **common
            ),
            WallSegment(
                id="wall-N", type=WallType.FACADE, start=[length_mm, width_mm], end=[0, width_mm], **common
            ),
            WallSegment(id="wall-W", type=WallType.FACADE, start=[0, width_mm], end=[0, 0], **common),
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
        *,
        provenance: Optional[ProvenanceRecord] = None,
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
                    provenance=provenance,
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
        *,
        provenance: Optional[ProvenanceRecord] = None,
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
                    provenance=provenance,
                )
            )
        return cores
