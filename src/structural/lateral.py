"""Lateral system candidate generator.

Identifies plausible lateral force-resisting systems: shear walls,
braced frames, moment frames, core walls, dual systems.  The output is
``LateralSystemCandidate`` objects, each scoped to a structural zone.
"""

from __future__ import annotations

import logging
import math

from src.schema.building_graph import BuildingGraph
from src.schema.enums import CoreType, WallType
from src.schema.structural_enums import LateralSystemType, StructuralZoneType
from src.schema.structural_graph import LateralSystemCandidate, StructuralZone
from src.structural.config import DEFAULT_CONFIG, StructuralConfig

logger = logging.getLogger(__name__)


class LateralSystemCandidateGenerator:
    def __init__(self, config: StructuralConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def generate(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> list[LateralSystemCandidate]:
        out: list[LateralSystemCandidate] = []
        out.extend(self._core_walls(graph, zones))
        out.extend(self._shear_walls(graph, zones))
        out.extend(self._braced_frames(graph, zones))
        out.extend(self._moment_frames(graph, zones))
        out.extend(self._dual_systems(out))
        out.sort(key=lambda c: c.plausibility, reverse=True)
        return out

    # ------------------------------------------------------------------

    def _core_walls(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> list[LateralSystemCandidate]:
        out: list[LateralSystemCandidate] = []
        core_zones = [z for z in zones if z.type == StructuralZoneType.CORE_SERVICE]
        if not core_zones or not graph.cores:
            return out

        # Check centering
        facade = graph.facade.perimeter_polygon
        if facade:
            xs = [p[0] for p in facade]
            ys = [p[1] for p in facade]
            fx = (min(xs) + max(xs)) / 2
            fy = (min(ys) + max(ys)) / 2
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
        else:
            fx = fy = 0.0
            width = height = 1.0

        for z in core_zones:
            cxs = [p[0] for p in z.polygon]
            cys = [p[1] for p in z.polygon]
            cx = sum(cxs) / len(cxs)
            cy = sum(cys) / len(cys)
            offset_frac = math.hypot(cx - fx, cy - fy) / max(math.hypot(width, height) / 2, 1.0)
            plaus = max(0.3, min(1.0, 1.0 - offset_frac))
            sym = "centered" if offset_frac < 0.2 else "off-center"
            out.append(LateralSystemCandidate(
                system_type=LateralSystemType.CORE_WALL,
                zone_id=z.id,
                polygon=z.polygon,
                plausibility=plaus,
                rationale=f"Core zone {sym} (offset fraction {offset_frac:.2f})",
                symmetry_contribution=sym,
            ))
        return out

    def _shear_walls(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> list[LateralSystemCandidate]:
        out: list[LateralSystemCandidate] = []
        cfg = self.config.lateral
        shear_walls = [w for w in graph.walls if w.type == WallType.SHEAR_WALL]
        if not shear_walls:
            # Still propose shear wall if no cores exist and there are structural walls
            struct = [w for w in graph.walls if w.type == WallType.STRUCTURAL]
            if not struct:
                return out
            long_walls = [w for w in struct
                          if math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1])
                             >= cfg.min_shear_wall_length_mm]
            if not long_walls:
                return out
            plaus = min(0.6, 0.3 + 0.05 * len(long_walls))
            rationale = "Long structural walls available to be converted to shear walls"
        else:
            plaus = min(1.0, 0.5 + 0.1 * len(shear_walls))
            rationale = f"{len(shear_walls)} explicit shear wall(s) present"

        perimeter_zone = next((z for z in zones if z.type == StructuralZoneType.CORE_SERVICE), None)
        target_zone = perimeter_zone or (zones[0] if zones else None)
        if target_zone is None:
            return out
        out.append(LateralSystemCandidate(
            system_type=LateralSystemType.SHEAR_WALL,
            zone_id=target_zone.id,
            polygon=target_zone.polygon,
            plausibility=plaus,
            rationale=rationale,
            symmetry_contribution="distributed",
        ))
        return out

    def _braced_frames(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> list[LateralSystemCandidate]:
        out: list[LateralSystemCandidate] = []
        cfg = self.config.lateral
        if not graph.grid.bays:
            return out
        suitable = [
            b for b in graph.grid.bays
            if cfg.min_braced_frame_bay_mm <= min(b.span_x_mm, b.span_y_mm) <= cfg.max_braced_frame_bay_mm
        ]
        if not suitable:
            return out
        plaus = min(0.8, 0.3 + 0.05 * len(suitable))
        target_zone = next((z for z in zones if z.type == StructuralZoneType.PERIMETER),
                           zones[0] if zones else None)
        if target_zone is None:
            return out
        out.append(LateralSystemCandidate(
            system_type=LateralSystemType.BRACED_FRAME,
            zone_id=target_zone.id,
            polygon=target_zone.polygon,
            plausibility=plaus,
            rationale=f"{len(suitable)} bays within braced-frame span range",
            symmetry_contribution="perimeter",
        ))
        return out

    def _moment_frames(
        self,
        graph: BuildingGraph,
        zones: list[StructuralZone],
    ) -> list[LateralSystemCandidate]:
        out: list[LateralSystemCandidate] = []
        if not graph.grid.bays:
            return out
        plaus = 0.4  # always plausible but never preferred absent other info
        target_zone = zones[0] if zones else None
        if target_zone is None:
            return out
        out.append(LateralSystemCandidate(
            system_type=LateralSystemType.MOMENT_FRAME,
            zone_id=target_zone.id,
            polygon=target_zone.polygon,
            plausibility=plaus,
            rationale="Moment frame always available given a regular grid",
            symmetry_contribution="distributed",
        ))
        return out

    def _dual_systems(
        self, existing: list[LateralSystemCandidate]
    ) -> list[LateralSystemCandidate]:
        has_core = any(c.system_type == LateralSystemType.CORE_WALL for c in existing)
        has_frame = any(
            c.system_type in {LateralSystemType.MOMENT_FRAME, LateralSystemType.BRACED_FRAME}
            for c in existing
        )
        if not (has_core and has_frame):
            return []
        # Use the strongest core zone for pairing
        core = next((c for c in existing if c.system_type == LateralSystemType.CORE_WALL), None)
        if core is None:
            return []
        plaus = min(1.0, core.plausibility + 0.1)
        return [
            LateralSystemCandidate(
                system_type=LateralSystemType.DUAL_SYSTEM,
                zone_id=core.zone_id,
                polygon=core.polygon,
                plausibility=plaus,
                rationale="Core + frame both plausible → dual system upgrade",
                symmetry_contribution="combined",
            )
        ]
