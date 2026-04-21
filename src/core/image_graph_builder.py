"""Channel C orchestrator — floor-plan image → :class:`BuildingGraph`.

Wires Stages 1-9 end-to-end for Channel C.  The worker task
(:func:`src.worker.tasks._run_image_pipeline`) owns the Celery
integration; this module owns the *pipeline itself* so it is
independently testable with in-memory fakes for every ML component.

Stage order:

1. **Stage 1 — Pre-processing** (``Preprocessor.preprocess`` +
   ``prepare_for_vlm``): full-resolution BGR for Stage 3+ plus a
   bandwidth-bounded PNG for Stage 2.
2. **Stage 2 — VLM classification** (``BuildingTypeClassifier``):
   building type drives manifest selection.
3. **Stage 3 — Wall segmentation** (``MLEngine.segment_walls``): U-Net
   primary with YOLO-Seg fallback, both resolved from the weights
   manifest for the classified building type.
4. **Stage 4 — Vectorisation** (``Vectorizer``): raster mask →
   collinear, endpoint-snapped line segments in millimetres.
5. **Stage 5 — Symbol detection** (``MLEngine.detect_symbols``):
   optional YOLOv8 pass for doors / windows / stairs.
6. **Stage 6-9 — Geometric post-processing**
   (``GeometryPostProcessor``): orthogonal snap, corner resolution,
   room polygon extraction, grid inference, column candidate scoring,
   core detection.
7. **Stage 10 — Assembly**: symbol bboxes → :class:`Opening` snapped
   to the nearest wall; :class:`Story`, :class:`Facade`,
   :class:`ProjectInfo`, :class:`ConfidenceScores`, and the
   :class:`BuildingMetadata` assumption register stitched together.
8. **Completeness gate** (``annotate_with_completeness``): the review
   UI decides human-approval flow from the resulting score.

Error behaviour — every ML component is allowed to degrade without
aborting the pipeline:

* **No API key / VLM parse failure** → ``classification.is_fallback``
  is ``True`` and the occupancy-derived building type is preserved.
* **No manifest slot resolvable** → the engine returns an empty mask
  with synthetic provenance; the graph carries zero walls and the
  "requires_human_review" warning fires via the completeness gate.
* **Zero vectorised walls** → the builder emits a schema-valid
  *degraded* graph (10 m placeholder extent, synthesised grid and
  facade) so the review UI always has something to render, with a
  loud ``image_pipeline_produced_no_walls`` warning plus an
  overrideable assumption.

Testing seam: the builder accepts optional injected
:class:`Preprocessor`, :class:`BuildingTypeClassifier`, and
``ml_engine_factory`` (callable ``(BuildingType, run_id) -> MLEngine``)
so integration tests can drive the full pipeline with synthetic wall
masks and zero actual torch / anthropic dependency.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import structlog

from src.config import settings
from src.core.geometry.config import GeometryPostProcessConfig
from src.core.geometry.post_processor import (
    GeometryInputs,
    GeometryOutputs,
    GeometryPostProcessor,
)
from src.cv.building_type_classifier import (
    BuildingTypeClassifier,
    ClassificationResult,
)
from src.cv.detector_adapters import SymbolDetection
from src.cv.ml_engine import MLEngine, SymbolDetectionResult, WallSegmentationResult
from src.cv.preprocessor import Preprocessor, VlmImagePayload
from src.cv.vectorizer import VectorizationConfig, Vectorizer
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
    DetectorSource,
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

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module constants — all documented per-field so the assumption register
# rationale can cite them without duplicating text.
# ---------------------------------------------------------------------------

_DEFAULT_NUM_STORIES = 1
_DEFAULT_F2F_MM = 3900.0
_DEFAULT_OCCUPANCY = OccupancyType.OFFICE
_DEFAULT_MATERIAL = MaterialPreference.REINFORCED_CONCRETE
_DEFAULT_BUILDING_CODE = "IBC 2021"

# Symbol-to-Opening conversion tolerances.
_OPENING_SNAP_TOL_MM = 1500.0  # drop a symbol if no wall is within 1.5 m
_DEFAULT_OPENING_WIDTH_MM = {
    OpeningType.DOOR: 900.0,
    OpeningType.WINDOW: 1200.0,
    OpeningType.GARAGE_DOOR: 2400.0,
    OpeningType.CURTAIN_WALL: 3000.0,
}

# Placeholder extent used when the full Channel-C pipeline collapses
# (zero wall output).  Picked so the graph is visibly-unreal to a
# reviewer but still schema-valid.  10 m × 10 m is small enough not
# to be mistaken for a real plan yet large enough to pass Story
# ``floor_area_gross_m2 >= 0`` and Facade ``perimeter_length_mm > 0``.
_DEGRADED_EXTENT_MM = 10_000.0

# Occupancy → BuildingType fallback table.  Must stay in lock-step
# with the one in :mod:`src.core.cad_graph_builder` and
# :mod:`src.core.graph_builder` — when the VLM classification fails
# we fall back to this occupancy-derived default so the reviewer is
# not handed an ``UNKNOWN`` building type on every degraded run.
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


# Factory signature.  Kept as a type alias so tests can write a
# one-line lambda and the signature stays self-documenting.
MLEngineFactory = Callable[[BuildingType, Optional[str]], MLEngine]


# ---------------------------------------------------------------------------
# Result bundles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageGraphBuildResult:
    """Everything :meth:`ImageGraphBuilder.build` produces.

    The :class:`BuildingGraph` is the primary payload; the extra
    fields let the worker (and any CLI / notebook) introspect how the
    pipeline behaved without re-parsing the assumption register.
    """

    graph: BuildingGraph
    classification: ClassificationResult
    vlm_payload: VlmImagePayload
    selected_slot: Optional[str]
    used_fallback_segmenter: bool
    primary_confidence: float
    symbol_count: int
    wall_count: int
    degraded: bool
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class ImageGraphBuilder:
    """Assemble a :class:`BuildingGraph` from a floor-plan image.

    Construct with optional dependency overrides; production wiring
    leaves them all ``None`` and the builder instantiates real
    components from the environment.  Tests inject synthetic doubles.

    Typical test usage::

        builder = ImageGraphBuilder(
            classifier=_FakeClassifier(BuildingType.RESIDENTIAL),
            ml_engine_factory=lambda bt, run: _fake_engine(bt, run),
        )
        result = builder.build(png_path, run_id="test-1")
    """

    def __init__(
        self,
        *,
        preprocessor: Optional[Preprocessor] = None,
        classifier: Optional[BuildingTypeClassifier] = None,
        ml_engine_factory: Optional[MLEngineFactory] = None,
        vectorizer_config: Optional[VectorizationConfig] = None,
        geometry_config: Optional[GeometryPostProcessConfig] = None,
    ) -> None:
        self._preprocessor = preprocessor or Preprocessor()
        self._classifier = classifier
        self._ml_engine_factory = ml_engine_factory
        self._vectorizer_config = vectorizer_config
        self._geometry_config = geometry_config

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build(
        self,
        image_path: str | Path,
        *,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
        project_name: Optional[str] = None,
        occupancy_type: Optional[OccupancyType] = None,
        material_preference: Optional[MaterialPreference] = None,
        num_stories: Optional[int] = None,
        floor_to_floor_mm: Optional[float] = None,
        scale_mm_per_px: Optional[float] = None,
    ) -> ImageGraphBuildResult:
        t0 = time.perf_counter()
        run_id = run_id or job_id or uuid.uuid4().hex
        job_id = job_id or run_id
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"image file not found: {image_path}")

        story_id = "story-0"
        occupancy = occupancy_type or _DEFAULT_OCCUPANCY
        material = material_preference or _DEFAULT_MATERIAL

        # --- Stage 1 ---------------------------------------------------
        processed = self._preprocessor.preprocess(image_path)
        original_bgr: np.ndarray = processed["original"]
        vlm_payload = self._preprocessor.prepare_for_vlm(image_path)

        # --- Stage 2 ---------------------------------------------------
        classifier = self._classifier or BuildingTypeClassifier(
            api_key=settings.anthropic_api_key
        )
        classification = classifier.classify(vlm_payload.png_bytes)

        # Pick the building type that drives manifest selection.  When
        # the VLM fails we fall back to the occupancy-derived type so
        # the ML engine still gets something sensible to route on.
        manifest_building_type = (
            classification.building_type
            if not classification.is_fallback
            else _OCCUPANCY_TO_BUILDING_TYPE.get(occupancy, BuildingType.UNKNOWN)
        )

        # --- Stage 3 — ML engine --------------------------------------
        ml_engine = self._make_ml_engine(manifest_building_type, run_id)

        # --- Stage 3 execution ----------------------------------------
        wall_result = ml_engine.segment_walls(original_bgr)
        sym_result = ml_engine.detect_symbols(original_bgr)

        # --- Stage 4 — Vectorise --------------------------------------
        vectorizer = Vectorizer(self._vectorizer_config)
        wall_dicts = vectorizer.vectorize(
            wall_result.mask, scale_mm_per_px=scale_mm_per_px
        )
        vect_stats = vectorizer.last_stats
        resolved_scale = (
            vect_stats.scale_mm_per_px
            if vect_stats is not None
            else (scale_mm_per_px or 1.0)
        )
        raw_walls = self._dicts_to_wall_segments(
            wall_dicts, wall_result=wall_result, story_id=story_id
        )

        # --- Stage 5-9 — Geometric post-processing --------------------
        geometry = GeometryPostProcessor(self._geometry_config).run(
            GeometryInputs(walls=raw_walls, story_id=story_id)
        )
        walls = geometry.walls

        # Some ML-produced walls have near-zero confidence (e.g. sub-
        # threshold primary with no fallback).  We do *not* discard
        # them here — the confidence is carried on each segment and
        # the review UI decides.  Only zero-wall cases trigger the
        # degraded branch below.
        degraded = not walls
        if degraded:
            graph = self._build_degraded_graph(
                job_id=job_id,
                run_id=run_id,
                project_name=project_name,
                occupancy=occupancy,
                material=material,
                num_stories=num_stories or _DEFAULT_NUM_STORIES,
                floor_to_floor_mm=floor_to_floor_mm or _DEFAULT_F2F_MM,
                classification=classification,
                manifest_building_type=manifest_building_type,
                vlm_payload=vlm_payload,
                wall_result=wall_result,
                sym_result=sym_result,
                selected_slot=ml_engine.primary_slot,
                geometry_assumptions=geometry.assumptions,
                elapsed=time.perf_counter() - t0,
            )
            return ImageGraphBuildResult(
                graph=graph,
                classification=classification,
                vlm_payload=vlm_payload,
                selected_slot=ml_engine.primary_slot,
                used_fallback_segmenter=wall_result.used_fallback,
                primary_confidence=wall_result.confidence,
                symbol_count=len(sym_result.detections),
                wall_count=0,
                degraded=True,
                notes=list(wall_result.notes) + list(sym_result.notes),
            )

        # --- Stories + facade + grid safeguard ------------------------
        stories, f2f_mm, used_default_f2f = self._build_stories(
            num_stories_override=num_stories,
            f2f_override=floor_to_floor_mm,
            occupancy=occupancy,
            rooms=geometry.rooms,
        )
        story_ids = [s.id for s in stories]
        for w in walls:
            w.stories = story_ids
        for room in geometry.rooms:
            room.story = story_ids[0]
        for core in geometry.cores:
            core.stories = story_ids

        # Grid: if post-processor produced too few lines to form a
        # bay, synthesise one from wall extents so the schema is
        # satisfied.  This happens on short plans where no interior
        # dividers crossed the support threshold.
        grid = self._ensure_grid(geometry.grid, walls)

        rooms = geometry.rooms or self._fallback_rooms(
            grid, story_ids[0], occupancy
        )

        facade = self._build_facade(grid)

        total_height = sum(s.floor_to_floor_mm for s in stories)
        project = ProjectInfo(
            name=project_name or image_path.stem or "Floor Plan",
            location=Location(lat=0.0, lng=0.0),
            occupancy_type=occupancy,
            material_preference=material,
            num_stories=len(stories),
            total_height_mm=total_height,
            building_code=_DEFAULT_BUILDING_CODE,
        )

        # --- Openings — bboxes → schema Openings ----------------------
        openings = self._symbols_to_openings(
            sym_result=sym_result,
            walls=walls,
            scale_mm_per_px=resolved_scale,
        )

        # --- Confidence scores ----------------------------------------
        confidence_scores = self._compute_confidence_scores(
            wall_result=wall_result,
            sym_result=sym_result,
            walls=walls,
            rooms=rooms,
            openings=openings,
            columns=geometry.columns,
            grid=grid,
        )

        # --- Assumption register --------------------------------------
        assumptions = self._build_assumption_register(
            classification=classification,
            manifest_building_type=manifest_building_type,
            vlm_payload=vlm_payload,
            selected_slot=ml_engine.primary_slot,
            wall_result=wall_result,
            sym_result=sym_result,
            geometry_assumptions=list(geometry.assumptions),
            used_default_f2f=used_default_f2f,
            f2f_mm=f2f_mm,
            occupancy_was_inferred=occupancy_type is not None,
            material_was_inferred=material_preference is not None,
            scale_was_inferred=vect_stats.scale_was_inferred if vect_stats else False,
            scale_mm_per_px=resolved_scale,
        )

        warnings = self._collect_warnings(
            wall_result=wall_result,
            sym_result=sym_result,
            walls=walls,
            rooms=rooms,
            openings=openings,
            geometry=geometry,
        )

        metadata = BuildingMetadata(
            job_id=job_id,
            input_source=InputSource.FLOOR_PLAN_IMAGE,
            inferred_building_type=manifest_building_type,
            confidence_scores=confidence_scores,
            assumption_register=assumptions,
            warnings=warnings,
            processing_time_seconds=round(time.perf_counter() - t0, 4),
        )

        graph = BuildingGraph(
            project=project,
            stories=stories,
            grid=grid,
            walls=walls,
            rooms=rooms,
            openings=openings,
            column_candidates=geometry.columns,
            cores=geometry.cores,
            facade=facade,
            metadata=metadata,
        )

        annotate_with_completeness(graph)

        logger.info(
            "image_graph_built",
            run_id=run_id,
            job_id=job_id,
            building_type=manifest_building_type.value,
            selected_slot=ml_engine.primary_slot,
            used_fallback=wall_result.used_fallback,
            walls=len(walls),
            rooms=len(rooms),
            openings=len(openings),
            columns=len(geometry.columns),
            cores=len(geometry.cores),
            assumptions=len(assumptions),
            completeness=graph.metadata.completeness.overall
            if graph.metadata.completeness
            else None,
        )

        return ImageGraphBuildResult(
            graph=graph,
            classification=classification,
            vlm_payload=vlm_payload,
            selected_slot=ml_engine.primary_slot,
            used_fallback_segmenter=wall_result.used_fallback,
            primary_confidence=wall_result.confidence,
            symbol_count=len(sym_result.detections),
            wall_count=len(walls),
            degraded=False,
            notes=list(wall_result.notes) + list(sym_result.notes),
        )

    # ------------------------------------------------------------------
    # Stage 3 — ML engine instantiation
    # ------------------------------------------------------------------

    def _make_ml_engine(
        self, building_type: BuildingType, run_id: str
    ) -> MLEngine:
        """Build or retrieve the MLEngine for this run.

        If the caller injected an ``ml_engine_factory`` we use it as-is
        — tests rely on this.  Otherwise we go through the production
        :class:`WeightsLoader` path.  A loader-level failure (missing
        manifest, environment mis-config) is logged and downgraded to
        an empty MLEngine so the pipeline degrades rather than aborts.
        """

        if self._ml_engine_factory is not None:
            return self._ml_engine_factory(building_type, run_id)

        try:
            from backend.weights.loader import WeightsLoader

            loader = WeightsLoader.from_env()
            return MLEngine.from_loader(
                loader, building_type=building_type, run_id=run_id
            )
        except Exception as exc:  # noqa: BLE001 — manifest / env error
            logger.warning(
                "ml_engine_loader_failed",
                building_type=building_type.value,
                error=str(exc),
            )
            return MLEngine(building_type=building_type, run_id=run_id)

    # ------------------------------------------------------------------
    # Stage 4 — wall dicts → schema
    # ------------------------------------------------------------------

    @staticmethod
    def _dicts_to_wall_segments(
        wall_dicts: list[dict],
        *,
        wall_result: WallSegmentationResult,
        story_id: str,
    ) -> list[WallSegment]:
        """Convert vectorizer output to schema :class:`WallSegment`.

        Provenance comes from the ML engine, so every wall the
        reviewer inspects can be traced back to the model (primary vs.
        fallback) that produced it.  Confidence is the segmentation
        confidence, not the vectorizer confidence; the vectorizer is
        deterministic post-hoc cleanup and doesn't have a meaningful
        "I am right" signal per segment.
        """

        provenance = wall_result.provenance
        walls: list[WallSegment] = []
        for i, d in enumerate(wall_dicts):
            walls.append(
                WallSegment(
                    id=f"wall-img-{i:04d}",
                    type=WallType.STRUCTURAL,
                    start=[round(float(d["start"][0]), 2), round(float(d["start"][1]), 2)],
                    end=[round(float(d["end"][0]), 2), round(float(d["end"][1]), 2)],
                    thickness_mm=float(d["thickness_mm"]),
                    stories=[story_id],
                    confidence=float(wall_result.confidence),
                    provenance=provenance,
                )
            )
        return walls

    # ------------------------------------------------------------------
    # Stories + grid + facade + rooms
    # ------------------------------------------------------------------

    def _build_stories(
        self,
        *,
        num_stories_override: Optional[int],
        f2f_override: Optional[float],
        occupancy: OccupancyType,
        rooms: list[Room],
    ) -> tuple[list[Story], float, bool]:
        """Return ``(stories, f2f_mm, used_default_f2f)``.

        Channel C has no reliable multi-story signal from a single
        floor plan image, so we honour the caller override if present
        and otherwise emit a single story — recorded as an assumption
        by the caller.
        """

        num = max(1, num_stories_override or _DEFAULT_NUM_STORIES)
        f2f = float(f2f_override or _DEFAULT_F2F_MM)
        used_default = f2f_override is None

        # Floor area: sum room polygons when available; otherwise we
        # have no footprint signal yet, so use 0 (the completeness
        # scorer picks this up).
        floor_area = sum(r.area_m2 for r in rooms) if rooms else 0.0

        stories: list[Story] = []
        for i in range(num):
            stories.append(
                Story(
                    id=f"story-{i}",
                    level=i,
                    floor_to_floor_mm=f2f,
                    elevation_mm=f2f * i,
                    floor_area_gross_m2=round(floor_area, 2),
                    usage=occupancy.value,
                )
            )
        return stories, f2f, used_default

    @staticmethod
    def _ensure_grid(grid: GridSystem, walls: list[WallSegment]) -> GridSystem:
        """If the post-processor emitted an empty grid, fabricate one from wall extents.

        The geometry post-processor only promotes wall clusters to
        grid lines when they have enough support; short plans can
        come back with 0 or 1 lines on an axis.  ``BuildingGraph``
        requires a :class:`Facade` whose perimeter depends on
        well-ordered grid extents, so we always emit at least a
        2×2 bounding-box grid.
        """

        if len(grid.x_lines) >= 2 and len(grid.y_lines) >= 2:
            return grid

        if not walls:
            return _empty_bbox_grid(0.0, _DEGRADED_EXTENT_MM, 0.0, _DEGRADED_EXTENT_MM)

        xs: list[float] = []
        ys: list[float] = []
        for w in walls:
            xs.extend((w.start[0], w.end[0]))
            ys.extend((w.start[1], w.end[1]))
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x0 == x1:
            x1 = x0 + _DEGRADED_EXTENT_MM
        if y0 == y1:
            y1 = y0 + _DEGRADED_EXTENT_MM
        return _empty_bbox_grid(x0, x1, y0, y1)

    @staticmethod
    def _build_facade(grid: GridSystem) -> Facade:
        x0 = grid.x_lines[0].position_mm
        x1 = grid.x_lines[-1].position_mm
        y0 = grid.y_lines[0].position_mm
        y1 = grid.y_lines[-1].position_mm
        polygon = rectangular_polygon_mm(x0, y0, x1, y1)
        length = 2 * ((x1 - x0) + (y1 - y0))
        if length <= 0:
            length = 1000.0
        return Facade(perimeter_polygon=polygon, perimeter_length_mm=length)

    @staticmethod
    def _fallback_rooms(
        grid: GridSystem, story_id: str, occupancy: OccupancyType
    ) -> list[Room]:
        """Synthesise a single whole-plan room when no geometry rooms exist.

        Channel C can produce a clean wall graph that still fails to
        enclose into faces (e.g. every wall is an exterior stroke).
        Rather than emit an empty rooms list — which looks like "the
        pipeline didn't run" — we emit one low-confidence
        :class:`Room` spanning the grid extents.
        """

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
                id=f"room-{story_id}",
                label=occupancy.value,
                type=rtype,
                polygon=polygon,
                area_m2=round(area, 2),
                story=story_id,
                perimeter_mm=round(perimeter, 2),
                confidence=0.40,
            )
        ]

    # ------------------------------------------------------------------
    # Stage 10 — symbols → openings
    # ------------------------------------------------------------------

    @staticmethod
    def _symbols_to_openings(
        *,
        sym_result: SymbolDetectionResult,
        walls: list[WallSegment],
        scale_mm_per_px: float,
    ) -> list[Opening]:
        """Snap each symbol bbox to the nearest wall; drop isolated detections.

        Symbol detections live in pixel coordinates.  We convert the
        bbox centre to millimetres via the vectoriser's scale, then
        run the same point-to-wall snap that CAD openings use.  A
        detection further than :data:`_OPENING_SNAP_TOL_MM` from any
        wall is discarded — almost always a false positive (a
        schedule marker, a dimension arrow).
        """

        if not walls or not sym_result.detections:
            return []

        openings: list[Opening] = []
        provenance = sym_result.provenance

        for idx, det in enumerate(sym_result.detections):
            opening_type = _symbol_class_to_opening_type(det.class_name)
            x1, y1, x2, y2 = det.bbox
            cx_px = (x1 + x2) * 0.5
            cy_px = (y1 + y2) * 0.5
            cx_mm = cx_px * scale_mm_per_px
            cy_mm = cy_px * scale_mm_per_px
            bbox_w_mm = max((x2 - x1) * scale_mm_per_px, 1.0)

            best_wall: Optional[WallSegment] = None
            best_dist = math.inf
            best_along = 0.0
            for wall in walls:
                dist, along = _point_to_segment_distance_and_projection(
                    (cx_mm, cy_mm), wall.start, wall.end
                )
                if dist < best_dist:
                    best_dist = dist
                    best_wall = wall
                    best_along = along

            if best_wall is None or best_dist > _OPENING_SNAP_TOL_MM:
                continue

            width_mm = max(
                bbox_w_mm, _DEFAULT_OPENING_WIDTH_MM.get(opening_type, 900.0) * 0.5
            )
            wall_length = distance_2d(best_wall.start, best_wall.end)
            position_mm = max(
                0.0, min(best_along, max(wall_length - width_mm, 0.0))
            )

            openings.append(
                Opening(
                    id=f"opening-img-{idx:04d}",
                    type=opening_type,
                    wall_id=best_wall.id,
                    position_mm=round(position_mm, 2),
                    width_mm=round(width_mm, 2),
                    confidence=float(det.confidence),
                    provenance=provenance,
                )
            )
        return openings

    # ------------------------------------------------------------------
    # Confidence + assumptions + warnings
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence_scores(
        *,
        wall_result: WallSegmentationResult,
        sym_result: SymbolDetectionResult,
        walls: list[WallSegment],
        rooms: list[Room],
        openings: list[Opening],
        columns: list[ColumnCandidate],
        grid: GridSystem,
    ) -> ConfidenceScores:
        """Compose per-subsystem confidence scores for Channel C.

        Values are calibrated against the Step-4 CAD scorer so the
        completeness report is comparable across channels:

        * ``wall_detection`` — the ML engine's reported confidence.
        * ``room_classification`` — ``None`` when no rooms exist, else
          modest default (rooms are inferred from geometry, not
          classified, until a VLM room-labeller lands).
        * ``grid_detection`` — low when the grid is the bbox fallback,
          high when it was inferred from actual wall clusters.
        * ``opening_detection`` — the symbol-detector confidence mean,
          or ``None`` when the detector is disabled.
        * ``column_inference`` — flat 0.60 for now: the post-processor
          emits columns only above its own threshold, but we don't
          calibrate against ground truth.
        """

        wall_score: Optional[float] = (
            round(float(wall_result.confidence), 2) if walls else None
        )
        room_score: Optional[float] = 0.55 if rooms else None
        # A two-by-two grid with all four lines landing exactly at the
        # wall extents is the "I had to fabricate this" shape; if the
        # grid has at least 3 lines on either axis it came from real
        # clustering.
        grid_score = (
            0.80 if (len(grid.x_lines) >= 3 or len(grid.y_lines) >= 3) else 0.45
        )
        if sym_result.enabled and openings:
            avg = sum(o.confidence for o in openings) / len(openings)
            opening_score: Optional[float] = round(float(avg), 2)
        else:
            opening_score = None
        column_score = 0.60 if columns else None
        dim_score = 0.50  # OCR not wired yet in Channel C

        components = [wall_score, grid_score, dim_score]
        for s in (room_score, opening_score, column_score):
            if s is not None:
                components.append(s)
        overall = (
            round(sum(components) / len(components), 2)
            if any(c is not None for c in components)
            else 0.0
        )
        return ConfidenceScores(
            wall_detection=wall_score,
            room_classification=room_score,
            grid_detection=grid_score,
            dimension_extraction=dim_score,
            opening_detection=opening_score,
            column_inference=column_score,
            overall=overall,
        )

    @staticmethod
    def _build_assumption_register(
        *,
        classification: ClassificationResult,
        manifest_building_type: BuildingType,
        vlm_payload: VlmImagePayload,
        selected_slot: Optional[str],
        wall_result: WallSegmentationResult,
        sym_result: SymbolDetectionResult,
        geometry_assumptions: list[AssumptionRecord],
        used_default_f2f: bool,
        f2f_mm: float,
        occupancy_was_inferred: bool,
        material_was_inferred: bool,
        scale_was_inferred: bool,
        scale_mm_per_px: float,
    ) -> list[AssumptionRecord]:
        register: list[AssumptionRecord] = []

        # VLM classification.  ``overrideable=True`` — the reviewer
        # may know this is a converted warehouse (INDUSTRIAL → MIXED_USE).
        register.append(
            AssumptionRecord.quick(
                id="channel_c_vlm_building_type",
                name="VLM-inferred building type",
                value=classification.building_type.value,
                source="src.cv.building_type_classifier",
                rationale=(
                    classification.rationale
                    if not classification.is_fallback
                    else "VLM unavailable — falling back to occupancy-derived "
                    "building type.  Override if the classification is wrong."
                ),
                confidence=classification.confidence,
                overrideable=True,
                affects_modules=[
                    "weights_manifest_selection",
                    "phase3.design",
                ],
            )
        )

        # VLM preprocessing — deterministic normalisation, not overrideable.
        register.append(
            AssumptionRecord.quick(
                id="channel_c_vlm_image_preprocess",
                name="VLM image preprocessing",
                value={
                    "encoded_width": vlm_payload.width,
                    "encoded_height": vlm_payload.height,
                    "original_width": vlm_payload.original_width,
                    "original_height": vlm_payload.original_height,
                    "dpi": vlm_payload.dpi,
                    "dpi_source": vlm_payload.dpi_source,
                    "was_rotated": vlm_payload.was_rotated,
                    "was_downscaled": vlm_payload.was_downscaled,
                },
                source="src.cv.preprocessor.prepare_for_vlm",
                rationale=(
                    "Image normalised for VLM round-trip: EXIF orientation "
                    "applied, downscaled to <=1568 px longest edge, PNG-encoded "
                    "under Claude's 5 MB ceiling.  Stage 3+ sees the full "
                    "resolution image separately."
                ),
                confidence=1.0,
                overrideable=False,
                affects_modules=["channel_c.stage_1"],
            )
        )

        # Manifest slot — deterministic given the building type.
        if selected_slot is not None:
            register.append(
                AssumptionRecord.quick(
                    id="channel_c_wall_segmenter_slot",
                    name="Selected wall-segmenter slot",
                    value=selected_slot,
                    source="backend.weights.loader",
                    rationale=(
                        "Slot resolved via kind=wall_segmenter + "
                        f"building_type={manifest_building_type.value}."
                    ),
                    confidence=1.0,
                    overrideable=False,
                    affects_modules=["stage3.wall_segmentation"],
                )
            )

        # ML-engine wall segmentation outcome — overrideable because a
        # reviewer may flag it as needing re-run (e.g. switch to fallback).
        register.append(
            AssumptionRecord.quick(
                id="channel_c_wall_segmentation",
                name="Wall segmentation outcome",
                value={
                    "primary_slot": wall_result.primary_slot,
                    "fallback_slot": wall_result.fallback_slot,
                    "used_fallback": wall_result.used_fallback,
                    "confidence": round(float(wall_result.confidence), 3),
                    "notes": list(wall_result.notes),
                },
                source="src.cv.ml_engine.MLEngine.segment_walls",
                rationale=(
                    "Primary U-Net / CubiCasa HG output; fallback engages "
                    "when the primary is below its manifest confidence "
                    "threshold or unavailable entirely."
                ),
                confidence=float(wall_result.confidence),
                overrideable=True,
                affects_modules=["stage3.wall_segmentation", "phase3.structure"],
            )
        )

        # Symbol-detector outcome.
        register.append(
            AssumptionRecord.quick(
                id="channel_c_symbol_detection",
                name="Symbol detection outcome",
                value={
                    "enabled": sym_result.enabled,
                    "slot": sym_result.slot,
                    "count": len(sym_result.detections),
                    "notes": list(sym_result.notes),
                },
                source="src.cv.ml_engine.MLEngine.detect_symbols",
                rationale=(
                    "Universal YOLOv8 door/window/stair detector.  Optional: "
                    "its absence only dings completeness, it never blocks a run."
                ),
                confidence=0.8 if sym_result.enabled else 0.0,
                overrideable=True,
                affects_modules=["stage3.openings"],
            )
        )

        # Scale provenance — the single biggest confound for ML walls.
        register.append(
            AssumptionRecord.quick(
                id="channel_c_scale_factor",
                name="Image scale factor",
                value=round(float(scale_mm_per_px), 4),
                unit="mm/px",
                source="src.cv.vectorizer.Vectorizer",
                rationale=(
                    "Scale derived from OCR dimensions when present; "
                    "otherwise inferred from the assumed building width "
                    "(10 m-100 m range)."
                    if scale_was_inferred
                    else "Scale supplied by OCR / caller."
                ),
                confidence=0.30 if scale_was_inferred else 0.90,
                overrideable=True,
                affects_modules=[
                    "stage4.vectorisation",
                    "stage9.geometry",
                    "phase3.structure",
                ],
            )
        )

        # Single-story + f2f defaults — always overrideable.
        register.append(
            AssumptionRecord.quick(
                id="channel_c_num_stories",
                name="Number of stories (Channel C default)",
                value=_DEFAULT_NUM_STORIES,
                source="src.core.image_graph_builder",
                rationale=(
                    "Channel C receives a single floor plan image and has "
                    "no multi-story signal.  Defaulted to 1 storey; "
                    "reviewer should override via the form."
                ),
                confidence=0.5,
                overrideable=True,
                affects_modules=["phase3.structure"],
            )
        )
        if used_default_f2f:
            register.append(
                AssumptionRecord.quick(
                    id="channel_c_f2f_default",
                    name="Floor-to-floor height default",
                    value=f2f_mm,
                    unit="mm",
                    source="src.core.image_graph_builder",
                    rationale=(
                        "Default commercial floor-to-floor (3.9 m) applied "
                        "because the image pipeline has no height signal."
                    ),
                    confidence=0.4,
                    overrideable=True,
                    affects_modules=["phase3.structure"],
                )
            )

        if not occupancy_was_inferred:
            register.append(
                AssumptionRecord.quick(
                    id="channel_c_occupancy_default",
                    name="Occupancy (Channel C default)",
                    value=_DEFAULT_OCCUPANCY.value,
                    source="src.core.image_graph_builder",
                    rationale=(
                        "Caller did not supply occupancy; defaulted to "
                        "OFFICE for Channel C.  Override via the review "
                        "endpoint or the upload form."
                    ),
                    confidence=0.4,
                    overrideable=True,
                    affects_modules=["phase3.design"],
                )
            )
        if not material_was_inferred:
            register.append(
                AssumptionRecord.quick(
                    id="channel_c_material_default",
                    name="Material preference default",
                    value=_DEFAULT_MATERIAL.value,
                    source="src.core.image_graph_builder",
                    rationale=(
                        "Caller did not supply material preference; "
                        "defaulted to reinforced concrete for Channel C."
                    ),
                    confidence=0.4,
                    overrideable=True,
                    affects_modules=["phase3.design"],
                )
            )

        # Geometry post-processor assumptions (snap, corners, rooms,
        # grid, columns, cores) — already stamped with overrideable=True
        # and the geometry source string.
        register.extend(geometry_assumptions)

        return register

    @staticmethod
    def _collect_warnings(
        *,
        wall_result: WallSegmentationResult,
        sym_result: SymbolDetectionResult,
        walls: list[WallSegment],
        rooms: list[Room],
        openings: list[Opening],
        geometry: GeometryOutputs,
    ) -> list[str]:
        warnings: list[str] = []
        if not walls:
            warnings.append("image_pipeline_produced_no_walls")
        if wall_result.used_fallback:
            warnings.append(
                f"wall_segmentation_used_fallback_slot:"
                f"{wall_result.fallback_slot or 'unknown'}"
            )
        if not rooms:
            warnings.append("room_extraction_produced_no_polygons")
        if not sym_result.enabled:
            warnings.append("symbol_detector_disabled_or_unresolved")
        if sym_result.enabled and not openings and sym_result.detections:
            warnings.append("symbol_detections_could_not_snap_to_walls")
        if not geometry.grid.x_lines or not geometry.grid.y_lines:
            warnings.append("grid_inferred_from_wall_bbox_fallback")
        return warnings

    # ------------------------------------------------------------------
    # Degraded path — zero-wall graceful emission
    # ------------------------------------------------------------------

    def _build_degraded_graph(
        self,
        *,
        job_id: str,
        run_id: str,
        project_name: Optional[str],
        occupancy: OccupancyType,
        material: MaterialPreference,
        num_stories: int,
        floor_to_floor_mm: float,
        classification: ClassificationResult,
        manifest_building_type: BuildingType,
        vlm_payload: VlmImagePayload,
        wall_result: WallSegmentationResult,
        sym_result: SymbolDetectionResult,
        selected_slot: Optional[str],
        geometry_assumptions: list[AssumptionRecord],
        elapsed: float,
    ) -> BuildingGraph:
        """Emit a schema-valid placeholder graph when Channel C collapses.

        The user still gets something to review (classification,
        assumption register, warnings) rather than a 500; the
        completeness scorer's human-review gate will flag it for
        triage automatically.
        """

        story_id = "story-0"
        grid = _empty_bbox_grid(0.0, _DEGRADED_EXTENT_MM, 0.0, _DEGRADED_EXTENT_MM)
        facade = self._build_facade(grid)
        stories, f2f, used_default_f2f = self._build_stories(
            num_stories_override=num_stories,
            f2f_override=floor_to_floor_mm,
            occupancy=occupancy,
            rooms=[],
        )
        rooms = self._fallback_rooms(grid, story_id, occupancy)
        total_height = sum(s.floor_to_floor_mm for s in stories)

        project = ProjectInfo(
            name=project_name or "Floor Plan (degraded)",
            location=Location(lat=0.0, lng=0.0),
            occupancy_type=occupancy,
            material_preference=material,
            num_stories=len(stories),
            total_height_mm=total_height,
            building_code=_DEFAULT_BUILDING_CODE,
        )

        # Loud degradation assumption — overrideable because a
        # reviewer can always re-run with a different scale / manifest
        # if they know why the first pass collapsed.
        degraded_record = AssumptionRecord.quick(
            id="channel_c_degraded_placeholder",
            name="Image pipeline produced no walls — placeholder graph emitted",
            value={
                "reason": "zero_walls_after_geometry_post_processor",
                "wall_segmentation_confidence": round(
                    float(wall_result.confidence), 3
                ),
                "primary_slot": wall_result.primary_slot,
                "fallback_slot": wall_result.fallback_slot,
                "used_fallback": wall_result.used_fallback,
            },
            source="src.core.image_graph_builder",
            rationale=(
                "The ML engine + vectoriser + geometry post-processor "
                "chain produced zero wall segments.  Common causes: no "
                "manifest weights resolved for the classified building "
                "type, segmentation confidence below threshold with no "
                "fallback slot available, or the vectoriser found no "
                "Hough lines.  A 10 m placeholder footprint has been "
                "emitted so the review UI has something to render."
            ),
            confidence=0.1,
            overrideable=True,
            affects_modules=["phase3.structure", "phase3.design"],
        )

        register = self._build_assumption_register(
            classification=classification,
            manifest_building_type=manifest_building_type,
            vlm_payload=vlm_payload,
            selected_slot=selected_slot,
            wall_result=wall_result,
            sym_result=sym_result,
            geometry_assumptions=geometry_assumptions,
            used_default_f2f=used_default_f2f,
            f2f_mm=f2f,
            occupancy_was_inferred=False,
            material_was_inferred=False,
            scale_was_inferred=True,
            scale_mm_per_px=1.0,
        )
        register.insert(0, degraded_record)

        warnings = [
            "image_pipeline_produced_no_walls",
            "degraded_placeholder_graph_emitted",
        ]
        if wall_result.used_fallback:
            warnings.append(
                f"wall_segmentation_used_fallback_slot:"
                f"{wall_result.fallback_slot or 'unknown'}"
            )
        if not sym_result.enabled:
            warnings.append("symbol_detector_disabled_or_unresolved")

        confidence_scores = ConfidenceScores(
            wall_detection=None,
            room_classification=None,
            grid_detection=None,
            dimension_extraction=None,
            opening_detection=None,
            column_inference=None,
            overall=0.0,
        )

        metadata = BuildingMetadata(
            job_id=job_id,
            input_source=InputSource.FLOOR_PLAN_IMAGE,
            inferred_building_type=manifest_building_type,
            confidence_scores=confidence_scores,
            assumption_register=register,
            warnings=warnings,
            processing_time_seconds=round(elapsed, 4),
        )

        graph = BuildingGraph(
            project=project,
            stories=stories,
            grid=grid,
            walls=[],
            rooms=rooms,
            openings=[],
            column_candidates=[],
            cores=[],
            facade=facade,
            metadata=metadata,
        )
        annotate_with_completeness(graph)
        return graph


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _empty_bbox_grid(x0: float, x1: float, y0: float, y1: float) -> GridSystem:
    """Build a minimal 2x2 grid from a bounding box.

    Used as the Channel-C grid fallback whenever the post-processor
    could not cluster enough wall support into distinct grid lines.
    The ``A``/``B``/``1``/``2`` ids line up with the convention the
    post-processor itself uses for real inferred grids — so the review
    UI renders both cases the same way.
    """

    x_lines = [
        GridLine(id="A", position_mm=round(x0, 2)),
        GridLine(id="B", position_mm=round(x1, 2)),
    ]
    y_lines = [
        GridLine(id="1", position_mm=round(y0, 2)),
        GridLine(id="2", position_mm=round(y1, 2)),
    ]
    bays = [
        Bay(
            id="bay-A-1",
            span_x_mm=round(x1 - x0, 2),
            span_y_mm=round(y1 - y0, 2),
            grid_x_start="A",
            grid_x_end="B",
            grid_y_start="1",
            grid_y_end="2",
        )
    ]
    return GridSystem(x_lines=x_lines, y_lines=y_lines, bays=bays)


def _symbol_class_to_opening_type(class_name: str) -> OpeningType:
    """Map a symbol-detector class label to an :class:`OpeningType`.

    Kept deliberately permissive: YOLO models trained on different
    datasets may emit ``"door"``, ``"Door"``, ``"DOOR"``, or
    ``"single-door"``.  Anything unrecognised falls back to ``DOOR``
    so no detection is silently lost — a reviewer can retype it.
    """

    lowered = class_name.lower()
    if "garage" in lowered:
        return OpeningType.GARAGE_DOOR
    if "curtain" in lowered:
        return OpeningType.CURTAIN_WALL
    if "window" in lowered:
        return OpeningType.WINDOW
    return OpeningType.DOOR


def _point_to_segment_distance_and_projection(
    pt: tuple[float, float] | list[float],
    seg_start: list[float],
    seg_end: list[float],
) -> tuple[float, float]:
    """Return ``(perpendicular_distance, projection_length_along_segment)``.

    Mirrors the helper in :mod:`src.core.cad_graph_builder`; kept
    local to avoid reaching into another module's private API.  Both
    helpers should eventually move to ``src.core.graph_utils`` once a
    third consumer appears.
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


__all__ = [
    "ImageGraphBuildResult",
    "ImageGraphBuilder",
    "MLEngineFactory",
]
