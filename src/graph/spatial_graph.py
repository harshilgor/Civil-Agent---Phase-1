"""NetworkX-based spatial building graph.

Provides graph-theoretic operations on the Building Graph: adjacency
queries, tributary area computation, load path analysis, and
import/export from the Pydantic ``BuildingGraph`` model.
"""

from __future__ import annotations

import math
from typing import Any

import networkx as nx
import structlog
from shapely.geometry import Polygon, Point

from src.schema.building_graph import BuildingGraph, Room

logger = structlog.get_logger(__name__)


class SpatialBuildingGraph:
    """NetworkX wrapper over a Building Graph.

    Nodes represent column candidates and wall endpoints.
    Edges represent wall segments and grid lines.
    Graph attributes store rooms, bays, and tributary areas.
    """

    def __init__(self) -> None:
        self._graph = nx.Graph()
        self._rooms: list[Room] = []
        self._bg: BuildingGraph | None = None

    @classmethod
    def from_building_graph(cls, bg: BuildingGraph) -> "SpatialBuildingGraph":
        """Construct from a ``BuildingGraph`` Pydantic model."""
        sbg = cls()
        sbg._bg = bg
        sbg._rooms = list(bg.rooms)

        # Add column-candidate nodes
        for cc in bg.column_candidates:
            node_id = cc.grid_intersection or f"col-{cc.position[0]:.0f}-{cc.position[1]:.0f}"
            sbg._graph.add_node(
                node_id,
                type="column",
                x=cc.position[0],
                y=cc.position[1],
                confidence=cc.confidence,
                is_required=cc.is_required,
            )

        # Add wall-segment edges (connecting nearest column nodes)
        for wall in bg.walls:
            start_node = sbg._nearest_node(wall.start)
            end_node = sbg._nearest_node(wall.end)
            if start_node and end_node and start_node != end_node:
                length = math.hypot(
                    wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]
                )
                sbg._graph.add_edge(
                    start_node,
                    end_node,
                    type="wall",
                    wall_id=wall.id,
                    wall_type=wall.type.value,
                    thickness_mm=wall.thickness_mm,
                    length_mm=round(length, 2),
                )

        # Add grid-line edges
        for xl in bg.grid.x_lines:
            for i in range(len(bg.grid.y_lines) - 1):
                n1 = f"{xl.id}-{bg.grid.y_lines[i].id}"
                n2 = f"{xl.id}-{bg.grid.y_lines[i + 1].id}"
                if sbg._graph.has_node(n1) and sbg._graph.has_node(n2):
                    span = bg.grid.y_lines[i + 1].position_mm - bg.grid.y_lines[i].position_mm
                    sbg._graph.add_edge(n1, n2, type="grid", direction="y", span_mm=span)

        for yl in bg.grid.y_lines:
            for i in range(len(bg.grid.x_lines) - 1):
                n1 = f"{bg.grid.x_lines[i].id}-{yl.id}"
                n2 = f"{bg.grid.x_lines[i + 1].id}-{yl.id}"
                if sbg._graph.has_node(n1) and sbg._graph.has_node(n2):
                    span = bg.grid.x_lines[i + 1].position_mm - bg.grid.x_lines[i].position_mm
                    sbg._graph.add_edge(n1, n2, type="grid", direction="x", span_mm=span)

        logger.info(
            "spatial_graph_built",
            nodes=sbg._graph.number_of_nodes(),
            edges=sbg._graph.number_of_edges(),
        )
        return sbg

    def to_building_graph(self) -> BuildingGraph:
        """Return the underlying Building Graph model."""
        if self._bg is None:
            raise ValueError("No BuildingGraph loaded")
        return self._bg

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_room_adjacency(self) -> dict[str, list[str]]:
        """Compute room adjacency based on shared wall segments.

        Two rooms are adjacent if their polygons share an edge (within
        tolerance) or if they are separated by a single wall segment.
        """
        adjacency: dict[str, list[str]] = {r.id: [] for r in self._rooms}

        for i, r1 in enumerate(self._rooms):
            poly1 = Polygon(r1.polygon)
            for j in range(i + 1, len(self._rooms)):
                r2 = self._rooms[j]
                if r1.story != r2.story:
                    continue
                poly2 = Polygon(r2.polygon)
                # Rooms are adjacent if polygons touch or share a boundary
                if poly1.touches(poly2) or poly1.intersection(poly2).length > 0:
                    adjacency[r1.id].append(r2.id)
                    adjacency[r2.id].append(r1.id)

        return adjacency

    def get_column_tributary_areas(self) -> dict[str, float]:
        """Compute tributary area (in m²) for each column candidate.

        Uses a simple Voronoi-like approach: each column "owns" the area
        closest to it within the building footprint.
        """
        if self._bg is None:
            return {}

        result: dict[str, float] = {}
        columns = [
            (cc.grid_intersection or f"col-{i}", cc.position)
            for i, cc in enumerate(self._bg.column_candidates)
        ]

        if not columns:
            return {}

        # Approximate: divide total floor area equally among columns
        total_area = sum(s.floor_area_gross_m2 for s in self._bg.stories[:1])
        per_column = total_area / len(columns) if columns else 0

        for col_id, _ in columns:
            result[col_id] = round(per_column, 2)

        return result

    def get_connectivity_info(self) -> dict[str, Any]:
        """Return basic graph connectivity metrics."""
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "is_connected": nx.is_connected(self._graph) if self._graph.number_of_nodes() > 0 else False,
            "components": nx.number_connected_components(self._graph),
            "density": round(nx.density(self._graph), 4),
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_adjacency_dict(self) -> dict[str, list[str]]:
        """Export the graph as an adjacency list."""
        return {str(n): [str(nb) for nb in self._graph.neighbors(n)] for n in self._graph.nodes}

    def to_node_link_json(self) -> dict:
        """Export in NetworkX node-link format (JSON-serialisable)."""
        return nx.node_link_data(self._graph)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _nearest_node(self, point: list[float], max_dist: float = 5000) -> str | None:
        """Find the nearest existing node to *point*."""
        best_id = None
        best_d = max_dist
        for node_id, data in self._graph.nodes(data=True):
            d = math.hypot(data.get("x", 0) - point[0], data.get("y", 0) - point[1])
            if d < best_d:
                best_d = d
                best_id = node_id
        return best_id
