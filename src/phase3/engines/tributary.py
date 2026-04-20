"""Tributary area engine.

For each support candidate on each story, compute a tributary polygon using
a Voronoi diagram (scipy) clipped to the floor polygon (Shapely). The cell
area in m^2 is the tributary area for that support.

All input coordinates are in millimeters; output areas are in m^2.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial import QhullError, Voronoi
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from ..assumptions import AssumptionBuilder
from ..models.loads import TributaryAreaResult
from ..models.outputs import Phase3Warning
from ..warnings import make_warning

#: Distance threshold in mm below which a Voronoi cell is considered to touch
#: a facade edge (classifies as edge / corner column).
FACADE_TOUCH_TOLERANCE_MM: float = 500.0

#: Multiplier applied to the facade bbox diagonal when placing the 4 ghost
#: points that bound the Voronoi diagram.
GHOST_POINT_MULTIPLIER: float = 10.0


def compute_tributary_areas(
    building_graph: dict[str, Any],
    structural_design_graph: dict[str, Any],
    assumption_builder: AssumptionBuilder,
) -> tuple[list[TributaryAreaResult], list[Phase3Warning]]:
    """Compute tributary areas for every support on every story.

    Args:
        building_graph: Phase 1 BuildingGraph as a dict.
        structural_design_graph: Phase 2 StructuralDesignGraph as a dict.
        assumption_builder: Shared assumption builder.

    Returns:
        Tuple of (tributary results, warnings emitted by this engine).
    """

    results: list[TributaryAreaResult] = []
    warnings: list[Phase3Warning] = []

    supports_by_story = _group_supports_by_story(structural_design_graph)
    floor_polygon_mm = _facade_polygon(building_graph)

    if floor_polygon_mm is None or floor_polygon_mm.area <= 0:
        warnings.append(make_warning("P3W011"))
        return results, warnings

    story_ids = [s.get("id") for s in building_graph.get("stories") or []]

    for story_id in story_ids:
        supports = supports_by_story.get(story_id, [])
        if not supports:
            warnings.append(
                make_warning("P3W012", affected_element_ids=[str(story_id)])
            )
            continue

        method, story_results, story_warnings = _tributary_for_story(
            story_id=story_id,
            supports=supports,
            floor_polygon_mm=floor_polygon_mm,
            assumption_builder=assumption_builder,
        )
        results.extend(story_results)
        warnings.extend(story_warnings)

        assumption_id = f"tributary_method_story_{story_id}"
        if not assumption_builder.has(assumption_id):
            assumption_builder.add(
                id=assumption_id,
                name=f"Tributary computation method for story {story_id}",
                value=method,
                unit=None,
                source="Phase 3 internal selection",
                confidence=0.95 if method == "voronoi_clipped" else 0.55,
                rationale=(
                    "Voronoi cells clipped to the facade polygon."
                    if method == "voronoi_clipped"
                    else "Fallback: equal area division (fewer than 3 supports or Voronoi failed)."
                ),
                overrideable=False,
                affects_modules=["tributary", "live_load", "combos", "member_demands"],
            )

    return results, warnings


def _tributary_for_story(
    *,
    story_id: str,
    supports: list[dict[str, Any]],
    floor_polygon_mm: Polygon,
    assumption_builder: AssumptionBuilder,
) -> tuple[str, list[TributaryAreaResult], list[Phase3Warning]]:
    """Compute tributary polygons for one story."""

    warnings: list[Phase3Warning] = []
    if len(supports) < 3:
        method = "equal_division_fallback"
        per_support_area_mm2 = floor_polygon_mm.area / max(len(supports), 1)
        results: list[TributaryAreaResult] = []
        for support in supports:
            results.append(
                _build_result(
                    support_id=support["id"],
                    story_id=story_id,
                    polygon_mm=floor_polygon_mm,
                    area_mm2=per_support_area_mm2,
                    facade_polygon_mm=floor_polygon_mm,
                    method=method,
                    assumption_builder=assumption_builder,
                )
            )
        warnings.append(
            make_warning(
                "P3W007",
                affected_element_ids=[str(story_id)],
                message_override=(
                    f"Story '{story_id}' has only {len(supports)} support candidate(s); "
                    "using equal area division instead of Voronoi."
                ),
            )
        )
        return method, results, warnings

    try:
        cells_mm = _voronoi_cells_clipped(
            [tuple(s["position"]) for s in supports], floor_polygon_mm
        )
    except (QhullError, ValueError) as exc:
        warnings.append(
            make_warning(
                "P3W007",
                affected_element_ids=[str(story_id)],
                message_override=(
                    f"Voronoi computation failed on story '{story_id}': {exc!s}. "
                    "Falling back to equal area division."
                ),
            )
        )
        per_support_area_mm2 = floor_polygon_mm.area / len(supports)
        results = [
            _build_result(
                support_id=s["id"],
                story_id=story_id,
                polygon_mm=floor_polygon_mm,
                area_mm2=per_support_area_mm2,
                facade_polygon_mm=floor_polygon_mm,
                method="equal_division_fallback",
                assumption_builder=assumption_builder,
            )
            for s in supports
        ]
        return "equal_division_fallback", results, warnings

    method = "voronoi_clipped"
    results = []
    for support, cell_mm in zip(supports, cells_mm):
        if cell_mm is None or cell_mm.is_empty or cell_mm.area <= 0:
            # Pathological case — skip this support.
            continue
        results.append(
            _build_result(
                support_id=support["id"],
                story_id=story_id,
                polygon_mm=cell_mm,
                area_mm2=float(cell_mm.area),
                facade_polygon_mm=floor_polygon_mm,
                method=method,
                assumption_builder=assumption_builder,
            )
        )

    return method, results, warnings


def _build_result(
    *,
    support_id: str,
    story_id: str,
    polygon_mm: BaseGeometry,
    area_mm2: float,
    facade_polygon_mm: Polygon,
    method: str,
    assumption_builder: AssumptionBuilder,
) -> TributaryAreaResult:
    """Assemble a TributaryAreaResult with edge / corner classification."""

    touched_edges = _count_facade_edges_touched(polygon_mm, facade_polygon_mm)
    is_corner = touched_edges >= 2
    is_edge = touched_edges == 1
    is_interior = touched_edges == 0

    tolerance_assumption = "facade_touch_tolerance_mm"
    if not assumption_builder.has(tolerance_assumption):
        assumption_builder.add(
            id=tolerance_assumption,
            name="Facade-edge touch tolerance for column classification",
            value=FACADE_TOUCH_TOLERANCE_MM,
            unit="mm",
            source="Phase 3 heuristic",
            confidence=0.90,
            rationale=(
                "A Voronoi cell within 500 mm of a facade edge is considered to be an "
                "edge column; two edges makes it a corner column."
            ),
            overrideable=False,
            affects_modules=["tributary", "live_load"],
        )

    return TributaryAreaResult(
        support_id=support_id,
        story_id=story_id,
        tributary_area_m2=area_mm2 / 1_000_000.0,
        polygon_wkt=polygon_mm.wkt,
        is_edge_column=is_edge,
        is_corner_column=is_corner,
        is_interior_column=is_interior,
        computation_method=method,
        assumption_ids=[
            f"tributary_method_story_{story_id}",
            tolerance_assumption,
        ],
    )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _facade_polygon(building_graph: dict[str, Any]) -> Polygon | None:
    """Return the facade polygon in mm, or ``None`` if unavailable/degenerate."""

    facade = building_graph.get("facade") or {}
    pts = facade.get("perimeter_polygon") or []
    if len(pts) < 3:
        return None
    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            return None
        return poly
    except (ValueError, TypeError):
        return None


def _group_supports_by_story(
    structural_design_graph: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Group support candidates by story id."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for support in structural_design_graph.get("support_candidates") or []:
        story_id = support.get("story")
        if story_id is None:
            continue
        grouped.setdefault(story_id, []).append(support)
    return grouped


def _voronoi_cells_clipped(
    points_mm: list[tuple[float, float]],
    floor_polygon_mm: Polygon,
) -> list[BaseGeometry | None]:
    """Return a Voronoi cell polygon clipped to the floor for each input point.

    The diagram is bounded by 4 ghost points placed far outside the floor bbox
    so that every input point receives a finite Voronoi region.
    """

    if len(points_mm) < 3:
        raise ValueError("Voronoi requires at least 3 non-collinear points")

    minx, miny, maxx, maxy = floor_polygon_mm.bounds
    dx = maxx - minx
    dy = maxy - miny
    radius = GHOST_POINT_MULTIPLIER * max(dx, dy, 1.0)
    cx = 0.5 * (minx + maxx)
    cy = 0.5 * (miny + maxy)

    ghost_points = [
        (cx - radius, cy - radius),
        (cx + radius, cy - radius),
        (cx + radius, cy + radius),
        (cx - radius, cy + radius),
    ]

    all_points = np.array(list(points_mm) + ghost_points, dtype=float)
    vor = Voronoi(all_points)

    cells: list[BaseGeometry | None] = []
    for idx in range(len(points_mm)):
        region_index = vor.point_region[idx]
        region = vor.regions[region_index]
        if not region or -1 in region:
            cells.append(None)
            continue
        vertices = [vor.vertices[v] for v in region]
        try:
            cell = Polygon(vertices)
            if not cell.is_valid:
                cell = cell.buffer(0)
            clipped = cell.intersection(floor_polygon_mm)
            cells.append(clipped if not clipped.is_empty else None)
        except (ValueError, TypeError):
            cells.append(None)

    return cells


def _count_facade_edges_touched(
    cell_polygon: BaseGeometry,
    facade_polygon: Polygon,
) -> int:
    """Count distinct facade edges that the cell touches within tolerance."""

    coords = list(facade_polygon.exterior.coords)
    if len(coords) < 2:
        return 0

    touched = 0
    for i in range(len(coords) - 1):
        edge = LineString([coords[i], coords[i + 1]])
        if edge.length <= 0:
            continue
        if cell_polygon.distance(edge) <= FACADE_TOUCH_TOLERANCE_MM:
            touched += 1
    return touched
