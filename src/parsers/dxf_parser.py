"""DXF file parser using ezdxf.

Extracts walls, grid lines, dimensions, rooms, doors, windows, and text
annotations from a DXF file.  Layer matching is **fuzzy** — it matches by
case-insensitive substring so it works across different firms' naming
conventions.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import ezdxf
import structlog
from ezdxf.document import Drawing
from ezdxf.layouts import BaseLayout

from src.utils.units import DXF_INSUNITS, to_mm

logger = structlog.get_logger(__name__)

# ── Layer-name matching patterns (substring, case-insensitive) ────────────
_WALL_PATTERNS = ["wall", "a-wall", "s-wall"]
_GRID_PATTERNS = ["grid", "axis", "column-grid", "s-grid", "a-grid"]
_DIM_PATTERNS = ["dim", "dims", "anno-dim", "a-dim"]
_ROOM_PATTERNS = ["room", "space", "area", "a-room", "a-area"]
_DOOR_PATTERNS = ["door", "a-door"]
_WINDOW_PATTERNS = ["window", "glaz", "a-glaz", "a-window"]
_COLUMN_PATTERNS = ["column", "s-col", "s-column"]


def _layer_matches(layer_name: str, patterns: list[str]) -> bool:
    """Return True if *layer_name* contains any of *patterns* (case-insensitive)."""
    low = layer_name.lower()
    return any(p in low for p in patterns)


class DXFParser:
    """Parse a DXF file and extract structural / architectural elements."""

    def parse(self, filepath: str | Path) -> dict[str, Any]:
        """Read *filepath* and return a dict of extracted elements.

        Keys: ``walls``, ``grid_lines``, ``dimensions``, ``rooms``,
        ``doors``, ``windows``, ``columns``, ``text_annotations``, ``units``.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"DXF file not found: {filepath}")

        doc = ezdxf.readfile(str(filepath))
        msp = doc.modelspace()
        units = self._detect_units(doc)

        result = {
            "walls": self._extract_walls(msp, units),
            "grid_lines": self._extract_grid_lines(msp, units),
            "dimensions": self._extract_dimensions(msp, units),
            "rooms": self._extract_rooms(msp, units),
            "doors": self._extract_doors(msp, units),
            "windows": self._extract_windows(msp, units),
            "columns": self._extract_columns(msp, units),
            "text_annotations": self._extract_text(msp),
            "units": units,
        }
        logger.info(
            "dxf_parsed",
            file=str(filepath),
            walls=len(result["walls"]),
            grid_lines=len(result["grid_lines"]["x_lines"]) + len(result["grid_lines"]["y_lines"]),
            rooms=len(result["rooms"]),
        )
        return result

    # ------------------------------------------------------------------
    # Entity extraction helpers
    # ------------------------------------------------------------------

    def _extract_walls(self, msp: BaseLayout, units: str) -> list[dict]:
        """Extract LINE and LWPOLYLINE entities from wall layers.

        For each entity pair of parallel lines the centerline and thickness
        are computed.  Single lines default to ``DEFAULT_THICKNESS_MM``.
        """
        DEFAULT_THICKNESS_MM = 200.0
        walls: list[dict] = []

        for entity in msp:
            if not _layer_matches(entity.dxf.layer, _WALL_PATTERNS):
                continue

            if entity.dxftype() == "LINE":
                start = self._to_mm_pt(entity.dxf.start, units)
                end = self._to_mm_pt(entity.dxf.end, units)
                walls.append({
                    "start": start,
                    "end": end,
                    "thickness_mm": DEFAULT_THICKNESS_MM,
                })

            elif entity.dxftype() == "LWPOLYLINE":
                points = list(entity.get_points(format="xy"))
                for i in range(len(points) - 1):
                    start = self._to_mm_pt(points[i], units)
                    end = self._to_mm_pt(points[i + 1], units)
                    walls.append({
                        "start": start,
                        "end": end,
                        "thickness_mm": DEFAULT_THICKNESS_MM,
                    })
                if entity.closed and len(points) >= 2:
                    start = self._to_mm_pt(points[-1], units)
                    end = self._to_mm_pt(points[0], units)
                    walls.append({"start": start, "end": end, "thickness_mm": DEFAULT_THICKNESS_MM})

        return walls

    def _extract_grid_lines(self, msp: BaseLayout, units: str) -> dict[str, list[dict]]:
        """Extract grid lines and classify into X and Y directions.

        A line is classified as X-direction if its predominant extent is
        horizontal (|dx| > |dy|), and Y-direction otherwise.
        """
        x_lines: list[dict] = []
        y_lines: list[dict] = []

        for entity in msp:
            if not _layer_matches(entity.dxf.layer, _GRID_PATTERNS):
                continue
            if entity.dxftype() != "LINE":
                continue

            start = self._to_mm_pt(entity.dxf.start, units)
            end = self._to_mm_pt(entity.dxf.end, units)
            dx = abs(end[0] - start[0])
            dy = abs(end[1] - start[1])

            entry = {"start": start, "end": end, "label": None}

            if dy > dx:
                entry["position_mm"] = round((start[0] + end[0]) / 2, 2)
                x_lines.append(entry)
            else:
                entry["position_mm"] = round((start[1] + end[1]) / 2, 2)
                y_lines.append(entry)

        x_lines.sort(key=lambda g: g["position_mm"])
        y_lines.sort(key=lambda g: g["position_mm"])
        return {"x_lines": x_lines, "y_lines": y_lines}

    def _extract_dimensions(self, msp: BaseLayout, units: str) -> list[dict]:
        """Extract DIMENSION entities — value and position."""
        dims: list[dict] = []
        for entity in msp:
            if not _layer_matches(entity.dxf.layer, _DIM_PATTERNS):
                if entity.dxftype() not in ("DIMENSION", "ALIGNED_DIMENSION"):
                    continue
            if entity.dxftype() not in ("DIMENSION", "ALIGNED_DIMENSION"):
                continue

            try:
                value_text = entity.dxf.get("text", "")
                measurement = getattr(entity.dxf, "actual_measurement", None)
                if measurement is not None:
                    value_mm = to_mm(measurement, units)
                else:
                    value_mm = self._parse_dimension_text(value_text, units)
                mid = entity.dxf.get("defpoint", (0, 0, 0))
                dims.append({
                    "text": value_text,
                    "value_mm": round(value_mm, 2) if value_mm else None,
                    "position": [round(mid[0], 2), round(mid[1], 2)],
                })
            except Exception:
                continue
        return dims

    def _extract_rooms(self, msp: BaseLayout, units: str) -> list[dict]:
        """Extract closed LWPOLYLINE / HATCH entities from room layers."""
        rooms: list[dict] = []
        for entity in msp:
            if not _layer_matches(entity.dxf.layer, _ROOM_PATTERNS):
                continue

            if entity.dxftype() == "LWPOLYLINE" and entity.closed:
                pts = [self._to_mm_pt(p, units) for p in entity.get_points(format="xy")]
                if pts:
                    pts.append(pts[0])
                rooms.append({"polygon": pts, "label": None})

            elif entity.dxftype() == "HATCH":
                for path in entity.paths:
                    if hasattr(path, "vertices"):
                        pts = [self._to_mm_pt(v[:2], units) for v in path.vertices]
                        if pts:
                            pts.append(pts[0])
                        rooms.append({"polygon": pts, "label": None})
        return rooms

    def _extract_doors(self, msp: BaseLayout, units: str) -> list[dict]:
        return self._extract_inserts(msp, _DOOR_PATTERNS, units, element_type="DOOR")

    def _extract_windows(self, msp: BaseLayout, units: str) -> list[dict]:
        return self._extract_inserts(msp, _WINDOW_PATTERNS, units, element_type="WINDOW")

    def _extract_columns(self, msp: BaseLayout, units: str) -> list[dict]:
        cols: list[dict] = []
        for entity in msp:
            if not _layer_matches(entity.dxf.layer, _COLUMN_PATTERNS):
                continue
            if entity.dxftype() == "INSERT":
                pos = self._to_mm_pt(entity.dxf.insert, units)
                cols.append({"position": pos})
            elif entity.dxftype() in ("CIRCLE", "LWPOLYLINE"):
                if entity.dxftype() == "CIRCLE":
                    pos = self._to_mm_pt(entity.dxf.center, units)
                    cols.append({"position": pos})
        return cols

    def _extract_text(self, msp: BaseLayout) -> list[dict]:
        """Extract all TEXT and MTEXT entities."""
        texts: list[dict] = []
        for entity in msp:
            if entity.dxftype() == "TEXT":
                texts.append({
                    "text": entity.dxf.text,
                    "position": [round(entity.dxf.insert[0], 2), round(entity.dxf.insert[1], 2)],
                    "layer": entity.dxf.layer,
                })
            elif entity.dxftype() == "MTEXT":
                texts.append({
                    "text": entity.text,
                    "position": [round(entity.dxf.insert[0], 2), round(entity.dxf.insert[1], 2)],
                    "layer": entity.dxf.layer,
                })
        return texts

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _extract_inserts(
        self, msp: BaseLayout, patterns: list[str], units: str, element_type: str,
    ) -> list[dict]:
        elements: list[dict] = []
        for entity in msp:
            if not _layer_matches(entity.dxf.layer, patterns):
                continue
            if entity.dxftype() == "INSERT":
                pos = self._to_mm_pt(entity.dxf.insert, units)
                elements.append({"type": element_type, "position": pos, "block_name": entity.dxf.name})
            elif entity.dxftype() == "LINE":
                start = self._to_mm_pt(entity.dxf.start, units)
                end = self._to_mm_pt(entity.dxf.end, units)
                mid = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
                length = math.hypot(end[0] - start[0], end[1] - start[1])
                elements.append({"type": element_type, "position": mid, "width_mm": round(length, 2)})
        return elements

    def _detect_units(self, doc: Drawing) -> str:
        """Detect drawing units from the $INSUNITS header variable."""
        try:
            insunits = doc.header.get("$INSUNITS", 0)
            return DXF_INSUNITS.get(insunits, "mm")
        except Exception:
            return "mm"

    @staticmethod
    def _to_mm_pt(point: tuple | list, units: str) -> list[float]:
        """Convert a 2-D/3-D point to mm and return [x, y]."""
        x = to_mm(float(point[0]), units)
        y = to_mm(float(point[1]), units)
        return [round(x, 2), round(y, 2)]

    @staticmethod
    def _parse_dimension_text(text: str, units: str) -> float | None:
        """Try to extract a numeric value from dimension text."""
        if not text:
            return None
        # Match patterns like "6000", "6,000", "6.5", "20'-0\""
        clean = text.replace(",", "").strip()
        m = re.match(r"^([\d.]+)", clean)
        if m:
            return to_mm(float(m.group(1)), units)
        return None
