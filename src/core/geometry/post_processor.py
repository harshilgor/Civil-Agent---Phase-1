"""Step 9 — :class:`GeometryPostProcessor` orchestrator.

Runs the six passes in order and assembles a :class:`GeometryOutputs`
bundle.  Channel B (CAD) inputs are preserved verbatim when provided;
Channel C (ML) pipeline inputs flow through every pass.

Every inference decision is recorded as an :class:`AssumptionRecord`
so the user's review UI can show which grid lines, columns, rooms,
and cores came from direct detection vs. were derived by the
post-processor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import structlog

from src.schema.assumptions import AssumptionRecord
from src.schema.building_graph import (
    ColumnCandidate,
    Core,
    GridSystem,
    Room,
    WallSegment,
)
from .columns import score_columns
from .config import GeometryPostProcessConfig
from .cores import detect_cores
from .corners import resolve_corners
from .grid import infer_grid
from .rooms import RoomHint, extract_rooms
from .snap import snap_orthogonal

# Every assumption the post-processor emits is sourced from the geometry
# pipeline itself — not a code table or external reference.  Keeping the
# source string constant means downstream consumers can filter on it.
_GEOMETRY_SOURCE = "Phase 1 / Step 9 / geometry post-processor"

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Input / output bundles
# ---------------------------------------------------------------------------


@dataclass
class GeometryInputs:
    """Everything the post-processor can be told about a plan up-front.

    Channel B (CAD) supplies authoritative values for ``rooms`` /
    ``grid`` / ``cad_columns`` / ``cad_cores``; Channel C (ML) leaves
    them ``None`` and the post-processor fills them in.  When both are
    provided the authoritative ones win and nothing is re-derived.
    """

    walls: list[WallSegment]
    rooms: Optional[list[Room]] = None
    grid: Optional[GridSystem] = None
    cad_columns: Optional[list[ColumnCandidate]] = None
    cad_cores: Optional[list[Core]] = None
    room_hints: Optional[list[RoomHint]] = None
    story_id: str = "S1"


@dataclass(frozen=True)
class GeometryOutputs:
    walls: list[WallSegment]
    rooms: list[Room]
    grid: GridSystem
    columns: list[ColumnCandidate]
    cores: list[Core]
    assumptions: list[AssumptionRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class GeometryPostProcessor:
    """Run the six-pass geometry pipeline.

    Construct once with a config (defaults or loaded from yaml) and
    call :meth:`run` per plan.  Stateless between runs.
    """

    def __init__(
        self,
        config: Optional[GeometryPostProcessConfig] = None,
    ) -> None:
        self.config = config or GeometryPostProcessConfig()

    def run(self, inputs: GeometryInputs) -> GeometryOutputs:
        assumptions: list[AssumptionRecord] = []

        # Passes 1 & 2 — snap + corners.  Always run.  Cleaning the
        # wall graph benefits both CAD and ML inputs: CAD walls can
        # have sub-millimetre imperfections from unit conversion, and
        # ML walls are the primary consumer.
        walls = snap_orthogonal(inputs.walls, self.config.snap)
        walls = resolve_corners(walls, self.config.corners)

        # Surface the snap/corners *policy* as explicit, overrideable
        # assumptions so a reviewer who knows the building has genuine
        # non-orthogonal geometry (30°/60° walls in some industrial or
        # curved-facade buildings) can disable them without a code
        # change.  AssumptionRecord.overrideable defaults to True in
        # :meth:`AssumptionRecord.quick`; we spell it out here because
        # these two records are the canonical "reviewer can change the
        # behaviour of Step 9" hooks.
        assumptions.append(
            _quick_assumption(
                id_="geometry.orthogonality_policy",
                name="Walls assumed orthogonal within angular tolerance",
                value=self.config.snap.angular_tolerance_deg,
                unit="deg",
                rationale=(
                    "Wall segments whose angle to the nearest cardinal "
                    "axis is within this tolerance are rotated onto the "
                    "axis during the snap pass.  Buildings with genuine "
                    "non-orthogonal geometry (industrial sheds with "
                    "angled walls, curved-facade towers, atria with "
                    "chamfered corners) should override this to a "
                    "smaller value — or to 0.0 to disable orthogonal "
                    "snapping entirely."
                ),
                confidence=0.75,
                overrideable=True,
            )
        )
        assumptions.append(
            _quick_assumption(
                id_="geometry.snap_weld_radius",
                name="Endpoint-weld radius for wall joints",
                value=self.config.snap.endpoint_weld_mm,
                unit="mm",
                rationale=(
                    "Two wall endpoints closer than this distance are "
                    "welded to a single vertex during the snap pass.  "
                    "Default 50 mm matches typical residential wall "
                    "thickness.  Increase for scans of heavy-construction "
                    "plans with thicker walls; decrease when the "
                    "vectoriser is known to produce tight endpoints."
                ),
                confidence=0.8,
                overrideable=True,
            )
        )
        assumptions.append(
            _quick_assumption(
                id_="geometry.corner_junction_radius",
                name="Junction radius for corner resolution",
                value=self.config.corners.junction_radius_mm,
                unit="mm",
                rationale=(
                    "Dangling endpoints within this radius of another "
                    "wall are extended / clipped to meet it.  Values "
                    "smaller than endpoint_weld_mm leave T-junctions "
                    "unresolved; values much larger pull distant walls "
                    "together and produce spurious joints."
                ),
                confidence=0.8,
                overrideable=True,
            )
        )

        # Pass 3 — rooms.  Preserve if Channel B already provided them.
        if inputs.rooms is not None:
            rooms = list(inputs.rooms)
        else:
            rooms = extract_rooms(
                walls,
                self.config.rooms,
                hints=inputs.room_hints,
                story_id=inputs.story_id,
            )
            assumptions.append(
                _quick_assumption(
                    id_="geometry.rooms_inferred",
                    name="Rooms inferred from wall geometry",
                    value=len(rooms),
                    rationale=(
                        f"{len(rooms)} rooms extracted by polygonising the "
                        "wall graph.  A Channel-B CAD upload would supply "
                        "authoritative room polygons instead."
                    ),
                )
            )

        # Pass 4 — grid.  Preserve Channel-B grid verbatim.
        if inputs.grid is not None and (inputs.grid.x_lines or inputs.grid.y_lines):
            grid = inputs.grid
        else:
            grid = infer_grid(walls, self.config.grid)
            if grid.x_lines or grid.y_lines:
                assumptions.append(
                    _quick_assumption(
                        id_="geometry.grid_inferred",
                        name="Structural grid inferred from wall clustering",
                        value={
                            "x_lines": len(grid.x_lines),
                            "y_lines": len(grid.y_lines),
                            "bays": len(grid.bays),
                        },
                        rationale=(
                            "Grid lines derived by clustering axis-aligned "
                            "walls along X and Y.  Requires at least three "
                            "walls of total length above the manifest floor "
                            "to emit a gridline."
                        ),
                    )
                )
            else:
                assumptions.append(
                    _quick_assumption(
                        id_="geometry.grid_absent",
                        name="No grid inferred",
                        value=False,
                        rationale=(
                            "Wall layout did not support grid inference "
                            "(insufficient collinear wall support).  "
                            "Downstream stages will treat this as a "
                            "gridless plan."
                        ),
                        confidence=0.5,
                    )
                )

        # Pass 5 — columns.  CAD columns always flow through as the
        # CAD signal; grid-intersection scoring still runs so we can
        # promote mid-intersection candidates the CAD export missed.
        columns = score_columns(
            walls,
            grid,
            self.config.columns,
            cad_columns=inputs.cad_columns,
        )
        if columns and inputs.cad_columns is None:
            assumptions.append(
                _quick_assumption(
                    id_="geometry.columns_inferred",
                    name="Column candidates inferred",
                    value=len(columns),
                    rationale=(
                        f"{len(columns)} column candidates scored from "
                        "wall-endpoint proximity and short-wall signals at "
                        "grid intersections.  Downstream structural analysis "
                        "decides which candidates become real columns."
                    ),
                )
            )

        # Pass 6 — cores.  Preserve CAD-supplied cores.
        if inputs.cad_cores is not None:
            cores = list(inputs.cad_cores)
        else:
            cores = detect_cores(rooms, self.config.cores)
            if cores:
                assumptions.append(
                    _quick_assumption(
                        id_="geometry.cores_inferred",
                        name="Vertical cores inferred from service rooms",
                        value=len(cores),
                        rationale=(
                            f"{len(cores)} cores assembled by clustering "
                            "contiguous stair / elevator / bathroom / MEP "
                            "rooms and wrapping the union in a convex hull."
                        ),
                    )
                )
            elif any(r.type in self.config.cores.seed_room_types for r in rooms):
                # There ARE seed rooms, but none survived the minimum
                # area filter — worth flagging so the user knows cores
                # were present but dropped as noise.
                assumptions.append(
                    _quick_assumption(
                        id_="geometry.cores_absent_despite_seeds",
                        name="Service rooms present but no core emitted",
                        value=False,
                        rationale=(
                            "Seed service rooms exist but no cluster cleared "
                            "the minimum cluster area threshold — check if "
                            "cores on this plan are individually small."
                        ),
                        confidence=0.5,
                    )
                )

        logger.info(
            "geometry_post_processor_complete",
            walls=len(walls),
            rooms=len(rooms),
            x_lines=len(grid.x_lines),
            y_lines=len(grid.y_lines),
            bays=len(grid.bays),
            columns=len(columns),
            cores=len(cores),
            assumptions=len(assumptions),
        )
        return GeometryOutputs(
            walls=walls,
            rooms=rooms,
            grid=grid,
            columns=columns,
            cores=cores,
            assumptions=assumptions,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quick_assumption(
    *,
    id_: str,
    name: str,
    value,
    rationale: str,
    confidence: float = 0.8,
    unit: Optional[str] = None,
    overrideable: bool = True,
) -> AssumptionRecord:
    """Thin wrapper around :meth:`AssumptionRecord.quick` that stamps
    every geometry-pipeline assumption with the same source string so
    downstream consumers can filter for them.

    All records emitted here default to ``overrideable=True``: a
    reviewer who knows the building violates one of our geometric
    priors (orthogonality, junction tolerance, service-room cluster
    definition) should be able to flag the assumption via the Phase 3
    review UI and re-run without a code change.
    """

    return AssumptionRecord.quick(
        id=id_,
        name=name,
        value=value,
        unit=unit,
        source=_GEOMETRY_SOURCE,
        rationale=rationale,
        confidence=confidence,
        overrideable=overrideable,
        affects_modules=["Phase 1 / Step 9 geometry"],
    )


__all__ = [
    "GeometryInputs",
    "GeometryOutputs",
    "GeometryPostProcessor",
]
