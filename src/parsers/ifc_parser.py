"""IFC file parser using IfcOpenShell.

Extracts walls, columns, spaces (rooms), stories, grid, doors, windows,
and project metadata from an IFC (Industry Foundation Classes) file.

Requires ``ifcopenshell`` — install via ``pip install ifcopenshell`` or
``conda install -c conda-forge ifcopenshell``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element
    import ifcopenshell.util.placement

    _HAS_IFC = True
except ImportError:
    _HAS_IFC = False


class IFCParserError(Exception):
    pass


class IFCParser:
    """Parse an IFC file and extract structural / architectural elements.

    All output coordinates are in **millimeters** regardless of the IFC
    file's internal units (IfcOpenShell usually reports in metres).
    """

    def __init__(self) -> None:
        if not _HAS_IFC:
            raise ImportError(
                "ifcopenshell is required for IFC parsing. "
                "Install with: pip install ifcopenshell"
            )

    def parse(self, filepath: str | Path) -> dict[str, Any]:
        """Read *filepath* and return a dict of extracted elements.

        Keys: ``walls``, ``columns``, ``rooms``, ``stories``, ``grid``,
        ``doors``, ``windows``, ``project_info``, ``units``.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"IFC file not found: {filepath}")

        ifc = ifcopenshell.open(str(filepath))
        length_unit = self._detect_length_unit(ifc)

        result = {
            "walls": self._extract_walls(ifc, length_unit),
            "columns": self._extract_columns(ifc, length_unit),
            "rooms": self._extract_spaces(ifc, length_unit),
            "stories": self._extract_stories(ifc, length_unit),
            "grid": self._extract_grid(ifc, length_unit),
            "doors": self._extract_doors(ifc, length_unit),
            "windows": self._extract_windows(ifc, length_unit),
            "project_info": self._extract_project(ifc),
            "units": "mm",
        }

        logger.info(
            "ifc_parsed",
            file=str(filepath),
            walls=len(result["walls"]),
            rooms=len(result["rooms"]),
            stories=len(result["stories"]),
        )
        return result

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def _extract_walls(self, ifc: Any, unit_factor: float) -> list[dict]:
        walls: list[dict] = []
        for wall in ifc.by_type("IfcWall"):
            try:
                placement = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
                x, y = placement[0][3] * unit_factor, placement[1][3] * unit_factor
                psets = ifcopenshell.util.element.get_psets(wall)
                length = self._get_quantity(psets, "Length", unit_factor, default=1000)
                thickness = self._get_quantity(psets, "Width", unit_factor, default=200)
                height = self._get_quantity(psets, "Height", unit_factor, default=3000)

                walls.append({
                    "start": [round(x, 2), round(y, 2)],
                    "end": [round(x + length, 2), round(y, 2)],
                    "thickness_mm": round(thickness, 2),
                    "height_mm": round(height, 2),
                    "name": wall.Name or "",
                    "global_id": wall.GlobalId,
                })
            except Exception as exc:
                logger.debug("ifc_wall_skip", id=wall.GlobalId, error=str(exc))
        return walls

    def _extract_columns(self, ifc: Any, unit_factor: float) -> list[dict]:
        columns: list[dict] = []
        for col in ifc.by_type("IfcColumn"):
            try:
                placement = ifcopenshell.util.placement.get_local_placement(col.ObjectPlacement)
                x, y = placement[0][3] * unit_factor, placement[1][3] * unit_factor
                columns.append({
                    "position": [round(x, 2), round(y, 2)],
                    "name": col.Name or "",
                    "global_id": col.GlobalId,
                })
            except Exception as exc:
                logger.debug("ifc_column_skip", id=col.GlobalId, error=str(exc))
        return columns

    def _extract_spaces(self, ifc: Any, unit_factor: float) -> list[dict]:
        spaces: list[dict] = []
        for space in ifc.by_type("IfcSpace"):
            try:
                placement = ifcopenshell.util.placement.get_local_placement(space.ObjectPlacement)
                x, y = placement[0][3] * unit_factor, placement[1][3] * unit_factor
                psets = ifcopenshell.util.element.get_psets(space)
                area = self._get_quantity(psets, "GrossFloorArea", 1.0, default=0)
                if area == 0:
                    area = self._get_quantity(psets, "NetFloorArea", 1.0, default=0)

                # IfcSpace doesn't always have geometry we can easily extract
                # as a polygon; store what we can.
                spaces.append({
                    "position": [round(x, 2), round(y, 2)],
                    "label": space.LongName or space.Name or "",
                    "area_m2": round(area, 2),
                    "global_id": space.GlobalId,
                    "polygon": None,
                })
            except Exception as exc:
                logger.debug("ifc_space_skip", id=space.GlobalId, error=str(exc))
        return spaces

    def _extract_stories(self, ifc: Any, unit_factor: float) -> list[dict]:
        stories: list[dict] = []
        for storey in ifc.by_type("IfcBuildingStorey"):
            elevation = (storey.Elevation or 0) * unit_factor
            stories.append({
                "name": storey.Name or f"Level {len(stories)}",
                "elevation_mm": round(elevation, 2),
                "global_id": storey.GlobalId,
            })
        stories.sort(key=lambda s: s["elevation_mm"])
        return stories

    def _extract_grid(self, ifc: Any, unit_factor: float) -> dict[str, list[dict]]:
        x_lines: list[dict] = []
        y_lines: list[dict] = []
        for grid in ifc.by_type("IfcGrid"):
            for axis in (grid.UAxes or []):
                label = axis.AxisTag or ""
                # Grid axis curves are IfcCurve — extract start point
                try:
                    curve = axis.AxisCurve
                    if hasattr(curve, "Points"):
                        pt = curve.Points[0].Coordinates
                        x_lines.append({
                            "label": label,
                            "position_mm": round(pt[0] * unit_factor, 2),
                        })
                except Exception:
                    pass
            for axis in (grid.VAxes or []):
                label = axis.AxisTag or ""
                try:
                    curve = axis.AxisCurve
                    if hasattr(curve, "Points"):
                        pt = curve.Points[0].Coordinates
                        y_lines.append({
                            "label": label,
                            "position_mm": round(pt[1] * unit_factor, 2),
                        })
                except Exception:
                    pass
        x_lines.sort(key=lambda g: g["position_mm"])
        y_lines.sort(key=lambda g: g["position_mm"])
        return {"x_lines": x_lines, "y_lines": y_lines}

    def _extract_doors(self, ifc: Any, unit_factor: float) -> list[dict]:
        return self._extract_openings(ifc, "IfcDoor", "DOOR", unit_factor)

    def _extract_windows(self, ifc: Any, unit_factor: float) -> list[dict]:
        return self._extract_openings(ifc, "IfcWindow", "WINDOW", unit_factor)

    def _extract_openings(
        self, ifc: Any, ifc_type: str, opening_type: str, unit_factor: float
    ) -> list[dict]:
        openings: list[dict] = []
        for elem in ifc.by_type(ifc_type):
            try:
                placement = ifcopenshell.util.placement.get_local_placement(elem.ObjectPlacement)
                x, y = placement[0][3] * unit_factor, placement[1][3] * unit_factor
                psets = ifcopenshell.util.element.get_psets(elem)
                width = self._get_quantity(psets, "OverallWidth", unit_factor, default=900 if opening_type == "DOOR" else 1200)
                height = self._get_quantity(psets, "OverallHeight", unit_factor, default=2100)
                openings.append({
                    "type": opening_type,
                    "position": [round(x, 2), round(y, 2)],
                    "width_mm": round(width, 2),
                    "height_mm": round(height, 2),
                    "name": elem.Name or "",
                    "global_id": elem.GlobalId,
                })
            except Exception as exc:
                logger.debug(f"ifc_{opening_type.lower()}_skip", id=elem.GlobalId, error=str(exc))
        return openings

    def _extract_project(self, ifc: Any) -> dict:
        projects = ifc.by_type("IfcProject")
        if not projects:
            return {"name": "Unknown", "description": ""}
        proj = projects[0]
        return {
            "name": proj.Name or "Unnamed Project",
            "description": proj.Description or "",
            "global_id": proj.GlobalId,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_length_unit(self, ifc: Any) -> float:
        """Return a factor to convert the IFC file's length unit to mm.

        IFC files commonly use metres.
        """
        try:
            units = ifc.by_type("IfcUnitAssignment")
            if units:
                for unit_set in units:
                    for unit in unit_set.Units:
                        if hasattr(unit, "UnitType") and unit.UnitType == "LENGTHUNIT":
                            name = getattr(unit, "Name", "METRE")
                            if name == "METRE":
                                prefix = getattr(unit, "Prefix", None)
                                if prefix == "MILLI":
                                    return 1.0
                                elif prefix == "CENTI":
                                    return 10.0
                                return 1000.0  # metres → mm
                            elif name == "FOOT":
                                return 304.8
                            elif name == "INCH":
                                return 25.4
        except Exception:
            pass
        return 1000.0  # default: metres

    @staticmethod
    def _get_quantity(
        psets: dict, key: str, unit_factor: float, default: float = 0
    ) -> float:
        """Search property sets for a quantity by name."""
        for pset_name, pset_vals in psets.items():
            if isinstance(pset_vals, dict) and key in pset_vals:
                val = pset_vals[key]
                if isinstance(val, (int, float)):
                    return val * unit_factor
        return default
