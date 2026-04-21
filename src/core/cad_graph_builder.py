"""Channel B orchestrator — parsed CAD / IFC → :class:`BuildingGraph`.

The DXF / IFC parsers in :mod:`src.parsers` hand us dict payloads with
raw walls, grid lines, rooms, openings, and columns.  This module
assembles those into a validated :class:`BuildingGraph` with the full
Step-2/4 semantics: every element carries a
:class:`~src.schema.provenance.ProvenanceRecord`, every default is
recorded as an :class:`~src.schema.assumptions.AssumptionRecord`, and
the completeness scorer is run before return.

This is the Channel B twin of
:meth:`src.core.graph_builder.GraphBuilder.from_structured_input`.  The
worker task in :mod:`src.worker.tasks.process_cad_file` drives it
end-to-end once the file has been parsed.
"""

from __future__ import annotations

import math
import time
import uuid
from typing import Any, Optional

import structlog

from src.parsers.grid_extractor import GridExtractor
from src.parsers.room_extractor import RoomExtractor
from src.parsers.wall_extractor import WallExtractor
from src.schema.assumptions import AssumptionRecord
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
    BuildingType,
    InputSource,
    MaterialPreference,
    OccupancyType,
    OpeningType,
    RoomType,
    WallType,
)
from src.schema.provenance import ProvenanceRecord
from src.utils.completeness_scorer import annotate_with_completeness
from src.utils.geometry import (
    distance_2d,
    polygon_area_m2,
    polygon_perimeter_mm,
    rectangular_polygon_mm,
)

from .cad_assumption_builder import CadAssumptionBuilder
from .provenance_helpers import cad_provenance
from .story_generator import StoryGenerator
from .zone_classifier import ZoneClassifier

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module constants — mirror the values in CadAssumptionBuilder so the
# defaults actually applied by the orchestrator stay in lock-step with the
# assumption rationales shown to the reviewer.
# ---------------------------------------------------------------------------

_DEFAULT_WALL_THICKNESS_MM = 200.0
_DEFAULT_F2F_MM = 3900.0
_DEFAULT_NUM_STORIES = 1
_DEFAULT_OCCUPANCY = OccupancyType.OFFICE
_DEFAULT_MATERIAL = MaterialPreference.REINFORCED_CONCRETE
_DEFAULT_BUILDING_CODE = "IBC 2021"
_DEFAULT_OPENING_SNAP_TOL_MM = 1500.0
_DEFAULT_OPENING_WIDTH_MM = {"DOOR": 900.0, "WINDOW": 1200.0}


# Channel A uses the same occupancy→BuildingType dispatch; keep the two
# mappings physically separate so either can evolve without dragging the
# other.
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


class CadGraphBuilder:
    """Build a :class:`BuildingGraph` from parsed CAD / IFC data."""

    def __init__(self) -> None:
        self._story_generator = StoryGenerator()
        self._zone_classifier = ZoneClassifier()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build(
        self,
        parsed_data: dict[str, Any],
        *,
        input_source: InputSource,
        project_name: Optional[str] = None,
        occupancy_type: Optional[OccupancyType] = None,
        material_preference: Optional[MaterialPreference] = None,
        num_stories: Optional[int] = None,
        floor_to_floor_mm: Optional[float] = None,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> BuildingGraph:
        """Assemble a validated graph from parser output.

        Parameters are intentionally permissive: any metadata the CAD file
        doesn't carry can be supplied by the caller (the upload form in a
        later step), or left ``None`` to trigger the Channel-B defaults
        (recorded in the assumption register).
        """

        if input_source not in {
            InputSource.DXF_FILE,
            InputSource.DWG_FILE,
            InputSource.IFC_FILE,
        }:
            raise ValueError(
                f"CadGraphBuilder does not handle input_source={input_source!r}"
            )

        t0 = time.perf_counter()
        run_id = run_id or job_id or uuid.uuid4().hex
        job_id = job_id or run_id

        provenance = cad_provenance(input_source=input_source, run_id=run_id)
        assumptions = CadAssumptionBuilder(input_source=input_source)
        assumptions.record_input_source_immutable()

        # --- Units + raw inputs -------------------------------------
        raw_units = str(parsed_data.get("units", "mm"))
        assumptions.record_unit_conversion(raw_units)

        # --- Walls --------------------------------------------------
        walls, default_thickness_used = self._build_walls(
            parsed_data, provenance=provenance, assumptions=assumptions
        )
        assumptions.record_default_wall_thickness(
            _DEFAULT_WALL_THICKNESS_MM, used_default=default_thickness_used
        )

        # --- Grid ---------------------------------------------------
        grid, grid_inferred, grid_from_walls = self._build_grid(
            parsed_data, walls=walls, assumptions=assumptions
        )

        # --- Stories / f2f -----------------------------------------
        stories, used_default_f2f, f2f_mm, story_ids = self._build_stories(
            parsed_data,
            grid=grid,
            num_stories_override=num_stories,
            floor_to_floor_override=floor_to_floor_mm,
            occupancy_type=occupancy_type or _DEFAULT_OCCUPANCY,
            assumptions=assumptions,
        )
        assumptions.record_f2f_fallback(f2f_mm, used_default=used_default_f2f)

        # Make sure wall.stories reflects the actual story ids we generated.
        for w in walls:
            w.stories = story_ids

        total_height = sum(s.floor_to_floor_mm for s in stories)

        # --- Rooms --------------------------------------------------
        rooms, synthesised_count = self._build_rooms(
            parsed_data,
            grid=grid,
            input_source=input_source,
            story_id=story_ids[0],
            provenance=provenance,
        )
        assumptions.record_room_polygon_synthesised(count=synthesised_count)

        # --- Openings ----------------------------------------------
        openings, opening_stats = self._build_openings(
            parsed_data, walls=walls, provenance=provenance
        )
        assumptions.record_opening_wall_association(
            total=opening_stats["total"], snapped=opening_stats["snapped"]
        )

        # --- Columns -----------------------------------------------
        column_candidates, cad_column_count = self._build_columns(
            parsed_data, grid=grid, walls=walls, provenance=provenance
        )
        assumptions.record_column_layer_found(count=cad_column_count)

        # --- Cores (heuristic on rooms) ----------------------------
        cores = self._zone_classifier.identify_cores(grid, rooms, walls)
        for core in cores:
            core.provenance = provenance
            core.stories = story_ids

        # --- Facade ------------------------------------------------
        facade = self._build_facade(grid, walls)

        # --- Occupancy / material metadata -------------------------
        occupancy = occupancy_type or _DEFAULT_OCCUPANCY
        material = material_preference or _DEFAULT_MATERIAL
        assumptions.record_occupancy_fallback(
            occupancy, was_inferred=occupancy_type is not None
        )
        assumptions.record_material_fallback(
            material, was_inferred=material_preference is not None
        )
        assumptions.record_building_code_default()
        assumptions.record_location_fallback()

        # --- Project info ------------------------------------------
        ifc_project_info = parsed_data.get("project_info") or {}
        project = ProjectInfo(
            name=project_name or ifc_project_info.get("name") or "CAD Import",
            location=Location(lat=0.0, lng=0.0),
            occupancy_type=occupancy,
            material_preference=material,
            num_stories=len(stories),
            total_height_mm=total_height,
            building_code=_DEFAULT_BUILDING_CODE,
        )

        # --- Confidence scores -------------------------------------
        confidence_scores = self._compute_confidence_scores(
            input_source=input_source,
            walls=walls,
            rooms=rooms,
            openings=openings,
            grid_inferred_from_walls=grid_from_walls,
            column_from_cad=cad_column_count > 0,
        )

        elapsed = round(time.perf_counter() - t0, 4)
        metadata = BuildingMetadata(
            job_id=job_id,
            input_source=input_source,
            inferred_building_type=_OCCUPANCY_TO_BUILDING_TYPE.get(
                occupancy, BuildingType.UNKNOWN
            ),
            confidence_scores=confidence_scores,
            assumptions_made=[],
            assumption_register=assumptions.records,
            warnings=self._collect_warnings(
                walls=walls, rooms=rooms, grid_inferred=grid_inferred
            ),
            processing_time_seconds=elapsed,
        )

        graph = BuildingGraph(
            project=project,
            stories=stories,
            grid=grid,
            walls=walls,
            rooms=rooms or self._fallback_rooms(grid, stories, occupancy, provenance),
            openings=openings,
            column_candidates=column_candidates,
            cores=cores,
            facade=facade,
            metadata=metadata,
        )

        annotate_with_completeness(graph)

        logger.info(
            "building_graph_built",
            source=input_source.value,
            run_id=run_id,
            job_id=job_id,
            walls=len(walls),
            rooms=len(rooms),
            openings=len(openings),
            columns=len(column_candidates),
            assumptions=len(metadata.assumption_register),
            elapsed_s=elapsed,
            completeness=graph.metadata.completeness.overall
            if graph.metadata.completeness
            else None,
        )
        return graph

    # ------------------------------------------------------------------
    # Walls
    # ------------------------------------------------------------------

    @staticmethod
    def _build_walls(
        parsed_data: dict[str, Any],
        *,
        provenance: ProvenanceRecord,
        assumptions: CadAssumptionBuilder,
    ) -> tuple[list[WallSegment], bool]:
        raw_walls = parsed_data.get("walls", []) or []
        extractor = WallExtractor()
        cleaned = extractor.extract(raw_walls)

        # Track whether any wall genuinely carried a thickness (e.g. IFC
        # Pset), so the assumption rationale reflects what actually
        # happened rather than always saying "default applied".
        used_default = True
        for w in cleaned:
            if abs(float(w.get("thickness_mm", 0)) - _DEFAULT_WALL_THICKNESS_MM) > 1e-6:
                used_default = False
                break

        wall_segments: list[WallSegment] = []
        for i, w in enumerate(cleaned):
            wall_segments.append(
                WallSegment(
                    id=f"wall-cad-{i:04d}",
                    type=WallType.STRUCTURAL,
                    start=[round(float(w["start"][0]), 2), round(float(w["start"][1]), 2)],
                    end=[round(float(w["end"][0]), 2), round(float(w["end"][1]), 2)],
                    thickness_mm=float(w["thickness_mm"]),
                    height_mm=float(w["height_mm"]) if w.get("height_mm") else None,
                    stories=["story-0"],  # replaced by caller after stories are built
                    material=None,
                    confidence=1.0,
                    provenance=provenance,
                )
            )

        # The layer-convention assumption wants to know how many layers
        # matched each pattern; for single-line DXFs we just report the
        # total entity counts.
        assumptions.record_layer_conventions(
            wall_hits=len(raw_walls),
            grid_hits=len(parsed_data.get("grid_lines", {}).get("x_lines", []))
            + len(parsed_data.get("grid_lines", {}).get("y_lines", [])),
            room_hits=len(parsed_data.get("rooms", [])),
        )

        return wall_segments, used_default

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    @staticmethod
    def _build_grid(
        parsed_data: dict[str, Any],
        *,
        walls: list[WallSegment],
        assumptions: CadAssumptionBuilder,
    ) -> tuple[GridSystem, bool, bool]:
        """Return ``(grid, any_grid_found, grid_was_inferred_from_walls)``."""

        # IFC parsers expose the grid under ``grid`` (with ``label`` keys),
        # DXF under ``grid_lines``.  Normalise.
        raw_grid: dict[str, list[dict]] = (
            parsed_data.get("grid")
            or parsed_data.get("grid_lines")
            or {"x_lines": [], "y_lines": []}
        )

        text_annotations = parsed_data.get("text_annotations", [])
        extractor = GridExtractor()
        grid_data = extractor.extract(raw_grid, text_annotations)

        x_lines: list[GridLine] = list(grid_data["x_lines"])
        y_lines: list[GridLine] = list(grid_data["y_lines"])
        any_grid_found = bool(x_lines or y_lines)

        inferred_from_walls = False
        if len(x_lines) < 2 or len(y_lines) < 2:
            # Fallback: infer from wall endpoints
            if walls:
                xs = sorted({round(w.start[0], 2) for w in walls} | {round(w.end[0], 2) for w in walls})
                ys = sorted({round(w.start[1], 2) for w in walls} | {round(w.end[1], 2) for w in walls})
                if len(xs) >= 2 and len(ys) >= 2:
                    x_lines = [GridLine(id=_grid_letter(i), position_mm=x) for i, x in enumerate(xs[:26])]
                    y_lines = [GridLine(id=str(i + 1), position_mm=y) for i, y in enumerate(ys)]
                    inferred_from_walls = True
                    assumptions.record_grid_inferred_from_walls()

        # Ultimate fallback: placeholder 10 m × 10 m bay so downstream
        # modules still have a well-formed grid to reason about.
        if len(x_lines) < 2 or len(y_lines) < 2:
            x_lines = [GridLine(id="A", position_mm=0), GridLine(id="B", position_mm=10000)]
            y_lines = [GridLine(id="1", position_mm=0), GridLine(id="2", position_mm=10000)]

        bays = _build_bays_from_lines(x_lines, y_lines)
        return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays), any_grid_found, inferred_from_walls

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------

    def _build_stories(
        self,
        parsed_data: dict[str, Any],
        *,
        grid: GridSystem,
        num_stories_override: Optional[int],
        floor_to_floor_override: Optional[float],
        occupancy_type: OccupancyType,
        assumptions: CadAssumptionBuilder,
    ) -> tuple[list[Story], bool, float, list[str]]:
        """Return ``(stories, used_default_f2f, f2f_mm, story_ids)``."""

        ifc_stories = parsed_data.get("stories") or []
        num_stories: int
        source_label: str

        if num_stories_override is not None:
            num_stories = max(1, num_stories_override)
            source_label = "caller_override"
        elif len(ifc_stories) >= 1:
            num_stories = len(ifc_stories)
            source_label = "ifc_building_storey"
        else:
            num_stories = _DEFAULT_NUM_STORIES
            source_label = "default"

        assumptions.record_num_stories_fallback(num_stories, source=source_label)

        # Floor-to-floor: derive from IFC storey elevation deltas when
        # possible; otherwise honour the caller override, otherwise default.
        derived_f2f: Optional[float] = None
        if len(ifc_stories) >= 2:
            elevations = sorted(float(s.get("elevation_mm", 0)) for s in ifc_stories)
            deltas = [
                elevations[i + 1] - elevations[i]
                for i in range(len(elevations) - 1)
                if elevations[i + 1] - elevations[i] > 0
            ]
            if deltas:
                derived_f2f = round(sum(deltas) / len(deltas), 2)

        if floor_to_floor_override is not None:
            f2f_mm = float(floor_to_floor_override)
            used_default = False
        elif derived_f2f is not None and derived_f2f >= 2400:
            f2f_mm = derived_f2f
            used_default = False
        else:
            f2f_mm = _DEFAULT_F2F_MM
            used_default = True

        # Floor area from the grid extents
        x_extent = grid.x_lines[-1].position_mm - grid.x_lines[0].position_mm
        y_extent = grid.y_lines[-1].position_mm - grid.y_lines[0].position_mm
        floor_area_m2 = max((x_extent * y_extent) / 1_000_000, 1.0)

        stories = self._story_generator.generate(
            num_stories=num_stories,
            floor_to_floor_mm=f2f_mm,
            occupancy_type=occupancy_type,
            floor_area_m2=floor_area_m2,
        )
        story_ids = [s.id for s in stories]
        return stories, used_default, f2f_mm, story_ids

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    @staticmethod
    def _build_rooms(
        parsed_data: dict[str, Any],
        *,
        grid: GridSystem,
        input_source: InputSource,
        story_id: str,
        provenance: ProvenanceRecord,
    ) -> tuple[list[Room], int]:
        raw_rooms = parsed_data.get("rooms", []) or []
        text_annotations = parsed_data.get("text_annotations", [])

        # IFC path: rooms arrive as {position, label, area_m2, polygon=None}.
        # DXF path: rooms arrive as {polygon, label=None}.  Treat them
        # uniformly by synthesising a placeholder polygon when the source
        # didn't provide one.
        synthesised = 0
        concrete_rooms: list[dict[str, Any]] = []
        for r in raw_rooms:
            poly = r.get("polygon")
            if poly and len(poly) >= 3:
                concrete_rooms.append(r)
                continue
            if "position" in r and r.get("area_m2", 0) > 0:
                cx, cy = r["position"]
                side = math.sqrt(max(float(r["area_m2"]), 1.0)) * 1000  # m -> mm
                half = side / 2
                concrete_rooms.append({
                    "polygon": rectangular_polygon_mm(cx - half, cy - half, cx + half, cy + half),
                    "label": r.get("label"),
                })
                synthesised += 1

        extractor = RoomExtractor()
        room_dicts = extractor.extract(concrete_rooms, text_annotations, story_id=story_id)
        rooms = [
            Room(
                id=rd["id"],
                label=rd["label"],
                type=RoomType(rd["type"]),
                polygon=rd["polygon"],
                area_m2=rd["area_m2"],
                story=rd["story"],
                perimeter_mm=rd.get("perimeter_mm"),
                confidence=1.0,
                provenance=provenance,
            )
            for rd in room_dicts
        ]
        return rooms, synthesised

    # ------------------------------------------------------------------
    # Openings
    # ------------------------------------------------------------------

    @staticmethod
    def _build_openings(
        parsed_data: dict[str, Any],
        *,
        walls: list[WallSegment],
        provenance: ProvenanceRecord,
    ) -> tuple[list[Opening], dict[str, int]]:
        doors = parsed_data.get("doors", []) or []
        windows = parsed_data.get("windows", []) or []
        total = len(doors) + len(windows)
        if total == 0 or not walls:
            return [], {"total": total, "snapped": 0}

        openings: list[Opening] = []
        snapped = 0

        for i, d in enumerate(doors):
            opening = _snap_opening_to_wall(
                element=d,
                element_idx=i,
                element_type=OpeningType.DOOR,
                walls=walls,
                provenance=provenance,
            )
            if opening is not None:
                openings.append(opening)
                snapped += 1

        for i, w in enumerate(windows):
            opening = _snap_opening_to_wall(
                element=w,
                element_idx=i,
                element_type=OpeningType.WINDOW,
                walls=walls,
                provenance=provenance,
            )
            if opening is not None:
                openings.append(opening)
                snapped += 1

        return openings, {"total": total, "snapped": snapped}

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def _build_columns(
        self,
        parsed_data: dict[str, Any],
        *,
        grid: GridSystem,
        walls: list[WallSegment],
        provenance: ProvenanceRecord,
    ) -> tuple[list[ColumnCandidate], int]:
        grid_candidates = self._zone_classifier.identify_columns(grid, walls=walls)
        for c in grid_candidates:
            c.provenance = provenance

        cad_columns = parsed_data.get("columns", []) or []
        for col in cad_columns:
            pos = col.get("position")
            if not pos or len(pos) < 2:
                continue
            grid_candidates.append(
                ColumnCandidate(
                    position=[round(float(pos[0]), 2), round(float(pos[1]), 2)],
                    confidence=0.95,
                    is_required=True,
                    notes="Detected from CAD column entity",
                    provenance=provenance,
                )
            )

        return grid_candidates, len(cad_columns)

    # ------------------------------------------------------------------
    # Facade / fallbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_facade(grid: GridSystem, walls: list[WallSegment]) -> Facade:
        x0 = grid.x_lines[0].position_mm
        x1 = grid.x_lines[-1].position_mm
        y0 = grid.y_lines[0].position_mm
        y1 = grid.y_lines[-1].position_mm
        perim = rectangular_polygon_mm(x0, y0, x1, y1)
        length = 2 * ((x1 - x0) + (y1 - y0))
        if length <= 0:
            # Unreachable in practice — grid build guarantees non-degenerate
            # extents — but the schema requires length > 0.
            length = 1000.0
        return Facade(perimeter_polygon=perim, perimeter_length_mm=length)

    @staticmethod
    def _fallback_rooms(
        grid: GridSystem,
        stories: list[Story],
        occupancy: OccupancyType,
        provenance: ProvenanceRecord,
    ) -> list[Room]:
        """When the CAD file has zero room polygons, synthesise one-per-floor
        matching the grid extents so the graph stays schema-valid."""

        x0, x1 = grid.x_lines[0].position_mm, grid.x_lines[-1].position_mm
        y0, y1 = grid.y_lines[0].position_mm, grid.y_lines[-1].position_mm
        polygon = rectangular_polygon_mm(x0, y0, x1, y1)
        area = polygon_area_m2(polygon)
        perimeter = polygon_perimeter_mm(polygon)
        type_map = {
            OccupancyType.OFFICE: RoomType.OFFICE,
            OccupancyType.RESIDENTIAL: RoomType.LIVING_ROOM,
        }
        rtype = type_map.get(occupancy, RoomType.UNDEFINED)

        return [
            Room(
                id=f"room-{s.id}",
                label=s.usage,
                type=rtype,
                polygon=polygon,
                area_m2=round(area, 2),
                story=s.id,
                perimeter_mm=round(perimeter, 2),
                confidence=0.60,
                provenance=provenance,
            )
            for s in stories
        ]

    # ------------------------------------------------------------------
    # Confidence / warnings
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence_scores(
        *,
        input_source: InputSource,
        walls: list[WallSegment],
        rooms: list[Room],
        openings: list[Opening],
        grid_inferred_from_walls: bool,
        column_from_cad: bool,
    ) -> ConfidenceScores:
        """CAD elements are authoritative, so the high bands sit at 0.95–1.0.

        IFC gets a small bonus over DXF because IFC classes are
        semantic (IfcWall, IfcSpace) whereas DXF leans on layer-name
        heuristics.  ``opening_detection`` is set to ``None`` — *not* 0.0 —
        when the file carries no openings, matching Channel A's convention
        so the completeness scorer can distinguish "subsystem didn't run"
        from "subsystem ran and failed" (see the ``_is_user_authoritative``
        branch in :mod:`src.utils.completeness_scorer`).
        """

        ifc_bonus = 0.05 if input_source == InputSource.IFC_FILE else 0.0

        wall_score = min(1.0, 0.90 + ifc_bonus) if walls else 0.0
        room_score: Optional[float]
        if rooms:
            labelled = sum(1 for r in rooms if r.label and not r.label.startswith("Room "))
            base = 0.85 if labelled / max(len(rooms), 1) >= 0.5 else 0.65
            room_score = round(min(1.0, base + ifc_bonus), 2)
        else:
            room_score = None

        grid_score = 0.55 if grid_inferred_from_walls else round(min(1.0, 0.90 + ifc_bonus), 2)

        dim_score = round(min(1.0, 0.85 + ifc_bonus), 2)

        opening_score = round(min(1.0, 0.80 + ifc_bonus), 2) if openings else None

        column_score = round(min(1.0, 0.85 + ifc_bonus), 2) if column_from_cad else 0.60

        components = [wall_score, grid_score, dim_score, column_score]
        components.extend(s for s in (room_score, opening_score) if s is not None)
        overall = round(sum(components) / len(components), 2) if components else 0.0

        return ConfidenceScores(
            wall_detection=round(wall_score, 2),
            room_classification=room_score,
            grid_detection=grid_score,
            dimension_extraction=dim_score,
            opening_detection=opening_score,
            column_inference=column_score,
            overall=overall,
        )

    @staticmethod
    def _collect_warnings(
        *,
        walls: list[WallSegment],
        rooms: list[Room],
        grid_inferred: bool,
    ) -> list[str]:
        warnings: list[str] = []
        if not walls:
            warnings.append("No walls extracted from source file")
        if not rooms:
            warnings.append("No room polygons extracted — synthesised default rooms")
        if grid_inferred:
            warnings.append("No grid / axis layer in source; grid inferred from wall endpoints")
        return warnings


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _grid_letter(i: int) -> str:
    """Return the CAD-grid X-axis label for index *i* (A, B, …, Z, AA, AB, …)."""

    if i < 26:
        return chr(ord("A") + i)
    first = chr(ord("A") + (i // 26) - 1)
    second = chr(ord("A") + (i % 26))
    return first + second


def _build_bays_from_lines(
    x_lines: list[GridLine], y_lines: list[GridLine]
) -> list[Bay]:
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


def _snap_opening_to_wall(
    *,
    element: dict[str, Any],
    element_idx: int,
    element_type: OpeningType,
    walls: list[WallSegment],
    provenance: ProvenanceRecord,
) -> Optional[Opening]:
    """Find the nearest wall to *element*'s position and emit an Opening.

    Returns ``None`` if the element is further than
    ``_DEFAULT_OPENING_SNAP_TOL_MM`` from any wall — such openings are
    almost always mis-categorised entities (schedule markers,
    dimensional tags) and are dropped rather than forced onto an
    unrelated wall.
    """

    pos = element.get("position") or [0, 0]
    width_mm = float(
        element.get("width_mm") or _DEFAULT_OPENING_WIDTH_MM[element_type.value]
    )
    height_mm = element.get("height_mm")

    best_wall: Optional[WallSegment] = None
    best_dist = math.inf
    best_along_mm = 0.0
    for wall in walls:
        dist, along = _point_to_segment_distance_and_projection(pos, wall.start, wall.end)
        if dist < best_dist:
            best_dist = dist
            best_wall = wall
            best_along_mm = along

    if best_wall is None or best_dist > _DEFAULT_OPENING_SNAP_TOL_MM:
        return None

    # Clip `position_mm` into the wall's own length so the schema
    # validator (`position_mm >= 0`) passes and downstream consumers
    # don't have to guard against negatives.
    wall_length = distance_2d(best_wall.start, best_wall.end)
    position_mm = max(0.0, min(best_along_mm, max(wall_length - width_mm, 0.0)))

    return Opening(
        id=f"{element_type.value.lower()}-{element_idx:04d}",
        type=element_type,
        wall_id=best_wall.id,
        position_mm=round(position_mm, 2),
        width_mm=width_mm,
        height_mm=float(height_mm) if height_mm else None,
        confidence=0.85,
        provenance=provenance,
    )


def _point_to_segment_distance_and_projection(
    pt: list[float] | tuple[float, ...],
    seg_start: list[float],
    seg_end: list[float],
) -> tuple[float, float]:
    """Return ``(perpendicular_distance, projection_length_along_segment)``.

    The projection is clipped to ``[0, segment_length]`` so ``position_mm``
    is always valid.
    """

    dx = seg_end[0] - seg_start[0]
    dy = seg_end[1] - seg_start[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return distance_2d(pt, seg_start), 0.0
    t = ((pt[0] - seg_start[0]) * dx + (pt[1] - seg_start[1]) * dy) / length_sq
    t_clipped = max(0.0, min(1.0, t))
    foot_x = seg_start[0] + t_clipped * dx
    foot_y = seg_start[1] + t_clipped * dy
    perp = math.hypot(pt[0] - foot_x, pt[1] - foot_y)
    length = math.sqrt(length_sq)
    return perp, t_clipped * length


__all__ = ["CadGraphBuilder"]
