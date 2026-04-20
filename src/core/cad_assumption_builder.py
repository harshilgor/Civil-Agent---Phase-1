"""Channel B (parsed CAD / IFC) → :class:`AssumptionRecord` emitter.

The DXF / IFC parsers in :mod:`src.parsers` extract whatever geometry and
metadata the source file actually carries; everything else the Phase 1
Building Graph needs (occupancy, material, number of stories when the
file only describes a single level, default wall thickness when a DXF
layer has lines but no width) is filled in here as an explicit
:class:`AssumptionRecord` so the review UI can audit and override it.

This is the Channel B twin of
:class:`src.core.assumption_builder.StructuredInputAssumptionBuilder`:
same contract, same override flow (``POST /api/v1/jobs/{job_id}/review``),
different source identifiers (``channel_b_*``) so the frontend can
filter assumptions by channel when a graph is later re-processed.
"""

from __future__ import annotations

from typing import Optional

from src.schema.assumptions import AssumptionRecord
from src.schema.enums import InputSource, MaterialPreference, OccupancyType


# ---------------------------------------------------------------------------
# Defaults Channel B falls back to when the CAD / IFC file is silent.
# ---------------------------------------------------------------------------

_DEFAULT_WALL_THICKNESS_MM = 200.0
_DEFAULT_F2F_MM = 3900.0
_DEFAULT_OCCUPANCY = OccupancyType.OFFICE
_DEFAULT_MATERIAL = MaterialPreference.REINFORCED_CONCRETE
_DEFAULT_NUM_STORIES = 1
_DEFAULT_BUILDING_CODE = "IBC 2021"


class CadAssumptionBuilder:
    """Translates parsed CAD data + Channel-B derivation steps into records.

    Same lifecycle as the Channel A builder: call ``record_*`` methods as
    the graph is assembled, then read :attr:`records` and attach the list
    to ``BuildingMetadata.assumption_register``.
    """

    _SOURCE_MODULE = "src.core.cad_graph_builder"

    def __init__(self, *, input_source: InputSource) -> None:
        self._input_source = input_source
        self._records: list[AssumptionRecord] = []

    @property
    def records(self) -> list[AssumptionRecord]:
        return list(self._records)

    # -- Source marker ------------------------------------------------------

    def record_input_source_immutable(self) -> None:
        """Pin the channel provenance so the UI can grey it out."""

        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_input_source",
                name="Input channel",
                value=self._input_source.value,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Channel B marker; identifies that the graph was parsed "
                    "directly from a CAD / IFC file."
                ),
                confidence=1.0,
                overrideable=False,
                affects_modules=["provenance"],
            )
        )

    # -- Units / conversion ------------------------------------------------

    def record_unit_conversion(self, source_units: str) -> None:
        """Record the CAD file's native unit system and the mm conversion."""

        already_mm = source_units.lower() in {"mm", "millimeter", "millimeters"}
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_unit_conversion",
                name="Source unit system",
                value=source_units,
                unit=None,
                source=f"{self._SOURCE_MODULE}.unit_detection",
                rationale=(
                    "Source file already authored in millimetres — no "
                    "conversion applied."
                    if already_mm
                    else f"Source authored in {source_units}; all geometry "
                    "converted to millimetres before graph assembly."
                ),
                # A mechanical conversion is exact; overrideable stays False.
                confidence=1.0,
                overrideable=False,
                affects_modules=["geometry.*"],
            )
        )

    # -- Layer / entity conventions ----------------------------------------

    def record_layer_conventions(
        self, *, wall_hits: int, grid_hits: int, room_hits: int
    ) -> None:
        """The DXF parser matches layers by fuzzy substring.  Record that.

        IFC callers can skip this — IFC classes are authoritative and the
        parser extracts ``IfcWall`` / ``IfcGrid`` / ``IfcSpace`` directly,
        without layer-name heuristics.
        """

        if self._input_source == InputSource.IFC_FILE:
            return
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_layer_conventions",
                name="Layer-name matching (fuzzy substring)",
                value={
                    "wall_layers_matched": wall_hits,
                    "grid_layers_matched": grid_hits,
                    "room_layers_matched": room_hits,
                },
                unit=None,
                source=f"{self._SOURCE_MODULE}.dxf_layer_match",
                rationale=(
                    "DXF entities were classified by case-insensitive "
                    "substring match against common layer names "
                    "(WALL / S-WALL, GRID / AXIS, ROOM / SPACE).  "
                    "Non-conforming layer schemes should be remapped "
                    "before upload or overridden via an explicit layer "
                    "mapping file in a future revision."
                ),
                confidence=0.80,
                overrideable=False,
                affects_modules=["dxf_parser"],
            )
        )

    # -- Wall / opening / column defaults ---------------------------------

    def record_default_wall_thickness(
        self, thickness_mm: float, *, used_default: bool
    ) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_wall_thickness_default",
                name="Wall thickness (when source is silent)",
                value=float(thickness_mm),
                unit="mm",
                source=f"{self._SOURCE_MODULE}.wall_thickness",
                rationale=(
                    f"DXF single-line walls carry no thickness attribute; "
                    f"default {_DEFAULT_WALL_THICKNESS_MM:.0f} mm applied."
                    if used_default
                    else "Thickness supplied by the source file (parallel "
                    "line pair or IFC Pset)."
                ),
                confidence=0.70 if used_default else 1.0,
                overrideable=True,
                affects_modules=["walls", "facade", "zone_classifier"],
            )
        )

    def record_opening_wall_association(
        self, *, total: int, snapped: int
    ) -> None:
        """How many openings were snapped to their nearest wall centre-line."""

        if total == 0:
            return
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_opening_wall_association",
                name="Opening → wall snapping",
                value={"total_openings": total, "snapped_to_nearest_wall": snapped},
                unit=None,
                source=f"{self._SOURCE_MODULE}.snap_openings",
                rationale=(
                    "CAD door / window blocks rarely reference the wall they "
                    "belong to, so each opening is snapped to the nearest "
                    "wall by centre-line distance.  Openings further than "
                    "the snap tolerance from any wall are dropped."
                ),
                confidence=0.75,
                overrideable=False,
                affects_modules=["openings", "walls"],
            )
        )

    # -- Program / building metadata --------------------------------------

    def record_occupancy_fallback(
        self, occupancy: OccupancyType, *, was_inferred: bool
    ) -> None:
        """CAD files rarely carry an occupancy field — record the fallback."""

        is_default = occupancy == _DEFAULT_OCCUPANCY and not was_inferred
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_occupancy_type",
                name="Occupancy / program",
                value=occupancy.value,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    f"Default {_DEFAULT_OCCUPANCY.value} — CAD / IFC files "
                    "typically do not record programme; supply explicitly "
                    "via the upload form for accurate Phase 3 loads."
                    if is_default
                    else "Inferred from the source file (IfcBuilding "
                    "property or text-annotation heuristic)."
                ),
                confidence=0.55 if is_default else 0.80,
                overrideable=True,
                affects_modules=["project", "phase3.live_loads"],
            )
        )

    def record_material_fallback(
        self, material: MaterialPreference, *, was_inferred: bool
    ) -> None:
        is_default = material == _DEFAULT_MATERIAL and not was_inferred
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_material_preference",
                name="Primary structural material",
                value=material.value,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Default Reinforced Concrete; CAD files rarely declare a "
                    "material explicitly.  Override for steel / timber / "
                    "masonry projects."
                    if is_default
                    else "Inferred from IFC material assignment or layer "
                    "naming."
                ),
                confidence=0.55 if is_default else 0.80,
                overrideable=True,
                affects_modules=["walls", "columns", "phase3.design"],
            )
        )

    def record_num_stories_fallback(
        self, num_stories: int, *, source: str
    ) -> None:
        """Number of stories.  IFC populates from IfcBuildingStorey;
        DXF falls back to a single level unless TEXT labels hint otherwise."""

        is_default = num_stories == _DEFAULT_NUM_STORIES and source == "default"
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_num_stories",
                name="Number of stories",
                value=int(num_stories),
                unit=None,
                source=f"{self._SOURCE_MODULE}.{source}",
                rationale=(
                    "Source did not disclose a story count; defaulting to a "
                    "single level.  Supply explicitly if the drawing covers "
                    "multiple floors."
                    if is_default
                    else f"Story count derived from {source}."
                ),
                confidence=0.50 if is_default else 0.90,
                overrideable=True,
                affects_modules=["stories", "story_generator"],
            )
        )

    def record_f2f_fallback(
        self, floor_to_floor_mm: float, *, used_default: bool
    ) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_floor_to_floor_height",
                name="Typical floor-to-floor height",
                value=float(floor_to_floor_mm),
                unit="mm",
                source=f"{self._SOURCE_MODULE}.floor_to_floor",
                rationale=(
                    f"Default {_DEFAULT_F2F_MM:.0f} mm applied — source "
                    "file did not include storey elevations."
                    if used_default
                    else "Derived from IfcBuildingStorey elevations."
                ),
                confidence=0.70 if used_default else 0.95,
                overrideable=True,
                affects_modules=["story_generator", "zone_classifier"],
            )
        )

    def record_building_code_default(self) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_building_code",
                name="Governing building code",
                value=_DEFAULT_BUILDING_CODE,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Default IBC 2021; supply explicitly for non-US projects."
                ),
                confidence=0.60,
                overrideable=True,
                affects_modules=["phase3.load_combinations"],
            )
        )

    # -- Geometry fallbacks ------------------------------------------------

    def record_location_fallback(self) -> None:
        """Null-island fallback when CAD has no geo-reference."""

        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_location",
                name="Project geographic location",
                value={"lat": 0.0, "lng": 0.0},
                unit="deg",
                source=f"{self._SOURCE_MODULE}.location",
                rationale=(
                    "CAD / IFC files typically lack geo-reference; defaulting "
                    "to (0, 0).  Override with the real site coordinates for "
                    "accurate wind / seismic loads in Phase 3."
                ),
                confidence=0.40,
                overrideable=True,
                affects_modules=["project.location", "phase3.environmental"],
            )
        )

    def record_grid_inferred_from_walls(self) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_grid_inferred_from_walls",
                name="Grid inferred from wall endpoints",
                value=True,
                unit=None,
                source=f"{self._SOURCE_MODULE}.grid_inference",
                rationale=(
                    "Source file did not expose a grid / axis layer; grid "
                    "lines were synthesised from unique wall endpoint "
                    "coordinates (X-direction and Y-direction)."
                ),
                confidence=0.60,
                overrideable=True,
                affects_modules=["grid", "zone_classifier"],
            )
        )

    def record_room_polygon_synthesised(self, *, count: int) -> None:
        if count == 0:
            return
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_room_polygon_synthesised",
                name="Room polygons synthesised from IFC spaces",
                value=count,
                unit=None,
                source=f"{self._SOURCE_MODULE}.synthesise_space_polygon",
                rationale=(
                    "IfcSpace entities do not always carry a 2-D footprint "
                    "that we can consume directly; a placeholder square of "
                    "area sqrt(GrossFloorArea) was generated around each "
                    "space's placement so downstream geometry stays valid."
                ),
                confidence=0.55,
                overrideable=True,
                affects_modules=["rooms"],
            )
        )

    def record_column_layer_found(self, *, count: int) -> None:
        if count == 0:
            return
        self._records.append(
            AssumptionRecord.quick(
                id="channel_b_columns_from_cad",
                name="Columns detected on CAD column layer",
                value=count,
                unit=None,
                source=f"{self._SOURCE_MODULE}.column_extraction",
                rationale=(
                    "Explicit column entities (INSERT / CIRCLE on a column "
                    "layer, or IfcColumn) were pulled from the source file "
                    "and merged into the zone-classifier's grid-inferred "
                    "candidates."
                ),
                confidence=0.85,
                overrideable=True,
                affects_modules=["column_candidates"],
            )
        )


__all__ = ["CadAssumptionBuilder"]
