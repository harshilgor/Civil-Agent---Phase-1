"""Structured-form → :class:`AssumptionRecord` emitter for Channel A.

Every default, fallback, or derivation that :meth:`GraphBuilder.from_structured_input`
makes on the way from a ``StructuredInputRequest`` to a ``BuildingGraph`` is
exposed here as an explicit auditable :class:`AssumptionRecord`.  That is the
contract Phase 3's optimiser and the review UI depend on — a silent default
the user never sees is a liability.

Each assumption carries:

* **id** — snake_case identifier, stable across runs (e.g.
  ``channel_a_wall_thickness_perimeter``).  Phase 3 and the frontend use this
  to drive the override flow (``POST /assumptions/{id}/override``).
* **value** / **unit** — the assumed value the graph was built against.
* **source** — where in the code the assumption came from (module path +
  function).  Makes the assumption greppable from a bug report.
* **confidence** — 1.0 when the user typed it; lower when we used a default
  because the form left the field blank; lower again when we derived it.
* **rationale** — why this value was chosen in plain English.
* **overrideable** — almost always True for structured input (the user
  provided the data; they can override the defaults).  The handful of
  hard constraints (e.g. ``input_source: STRUCTURED_FORM``) are flagged
  False so the review UI can grey them out.
* **affects_modules** — downstream modules the assumption materially
  changes the output of (grid_generator, span_calculator, zone_classifier,
  story_generator).
"""

from __future__ import annotations

from typing import Optional

from src.schema.assumptions import AssumptionRecord
from src.schema.input_models import StructuredInputRequest


# ---------------------------------------------------------------------------
# Defaults pulled from the pydantic input model.  Kept in sync via unit
# tests in tests/test_structured_input_assumptions.py so drift fails loud.
# ---------------------------------------------------------------------------

_DEFAULT_F2F_MM = 3900.0
_DEFAULT_PREFERRED_BAY_MM = 8000.0
_DEFAULT_MIN_BAY_MM = 4000.0
_DEFAULT_MAX_BAY_MM = 15000.0
_DEFAULT_WALL_THICKNESS_MM = 200.0
_DEFAULT_BUILDING_CODE = "IBC 2021"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class StructuredInputAssumptionBuilder:
    """Translates a :class:`StructuredInputRequest` + derivation steps into a
    flat list of :class:`AssumptionRecord` objects.

    The builder is stateful: call the ``record_*`` methods as the graph is
    being assembled; each call appends one :class:`AssumptionRecord` to the
    internal list.  Callers retrieve the accumulated list via :attr:`records`
    and attach it to ``BuildingMetadata.assumption_register``.
    """

    # Source tag embedded in every record so the review UI can filter by
    # originating channel.
    _SOURCE_MODULE = "src.core.graph_builder.from_structured_input"

    def __init__(self) -> None:
        self._records: list[AssumptionRecord] = []

    @property
    def records(self) -> list[AssumptionRecord]:
        return list(self._records)

    # -- Form defaults -----------------------------------------------------

    def record_floor_to_floor(self, request: StructuredInputRequest) -> None:
        is_default = request.floor_to_floor_mm == _DEFAULT_F2F_MM
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_floor_to_floor_height",
                name="Typical floor-to-floor height",
                value=float(request.floor_to_floor_mm),
                unit="mm",
                source=self._SOURCE_MODULE,
                rationale=(
                    "Left at the structured-form default of "
                    f"{_DEFAULT_F2F_MM:.0f} mm (IBC-friendly office/residential "
                    "typical)."
                    if is_default
                    else "User-supplied in the structured-form payload."
                ),
                confidence=0.80 if is_default else 1.0,
                overrideable=True,
                affects_modules=["story_generator", "zone_classifier"],
            )
        )

    def record_ground_floor_height(self, request: StructuredInputRequest) -> None:
        if request.ground_floor_height_mm is None:
            self._records.append(
                AssumptionRecord.quick(
                    id="channel_a_ground_floor_height",
                    name="Ground-floor-to-floor height",
                    value=float(request.floor_to_floor_mm),
                    unit="mm",
                    source=self._SOURCE_MODULE,
                    rationale=(
                        "No explicit ground-floor height supplied; reusing the "
                        "typical floor-to-floor height.  Taller lobbies should "
                        "be specified via ``ground_floor_height_mm``."
                    ),
                    confidence=0.75,
                    overrideable=True,
                    affects_modules=["story_generator"],
                )
            )
        else:
            self._records.append(
                AssumptionRecord.quick(
                    id="channel_a_ground_floor_height",
                    name="Ground-floor-to-floor height",
                    value=float(request.ground_floor_height_mm),
                    unit="mm",
                    source=self._SOURCE_MODULE,
                    rationale="User-supplied taller-ground-floor override.",
                    confidence=1.0,
                    overrideable=True,
                    affects_modules=["story_generator"],
                )
            )

    def record_bay_preferences(self, request: StructuredInputRequest) -> None:
        def _is_default(value: float, default: float) -> bool:
            return abs(value - default) < 1e-6

        self._records.extend(
            [
                AssumptionRecord.quick(
                    id="channel_a_preferred_bay_x",
                    name="Preferred X-direction bay size",
                    value=float(request.preferred_bay_x_mm),
                    unit="mm",
                    source=f"{self._SOURCE_MODULE}.grid_generator",
                    rationale=(
                        f"Default {_DEFAULT_PREFERRED_BAY_MM:.0f} mm applied; "
                        "actual bay sizes may be adjusted by the divider to "
                        "honour length and constraints."
                        if _is_default(request.preferred_bay_x_mm, _DEFAULT_PREFERRED_BAY_MM)
                        else "User-supplied preferred bay size."
                    ),
                    confidence=0.85
                    if _is_default(request.preferred_bay_x_mm, _DEFAULT_PREFERRED_BAY_MM)
                    else 1.0,
                    overrideable=True,
                    affects_modules=["grid_generator", "zone_classifier"],
                ),
                AssumptionRecord.quick(
                    id="channel_a_preferred_bay_y",
                    name="Preferred Y-direction bay size",
                    value=float(request.preferred_bay_y_mm),
                    unit="mm",
                    source=f"{self._SOURCE_MODULE}.grid_generator",
                    rationale=(
                        f"Default {_DEFAULT_PREFERRED_BAY_MM:.0f} mm applied; "
                        "actual bay sizes may be adjusted by the divider to "
                        "honour width and constraints."
                        if _is_default(request.preferred_bay_y_mm, _DEFAULT_PREFERRED_BAY_MM)
                        else "User-supplied preferred bay size."
                    ),
                    confidence=0.85
                    if _is_default(request.preferred_bay_y_mm, _DEFAULT_PREFERRED_BAY_MM)
                    else 1.0,
                    overrideable=True,
                    affects_modules=["grid_generator", "zone_classifier"],
                ),
                AssumptionRecord.quick(
                    id="channel_a_min_bay",
                    name="Minimum allowable bay size",
                    value=float(request.min_bay_mm),
                    unit="mm",
                    source=f"{self._SOURCE_MODULE}.grid_generator",
                    rationale=(
                        "Below this, bays are merged.  Default "
                        f"{_DEFAULT_MIN_BAY_MM:.0f} mm reflects a reasonable "
                        "lower bound for structural framing."
                        if _is_default(request.min_bay_mm, _DEFAULT_MIN_BAY_MM)
                        else "User-supplied structural minimum."
                    ),
                    confidence=0.80
                    if _is_default(request.min_bay_mm, _DEFAULT_MIN_BAY_MM)
                    else 1.0,
                    overrideable=True,
                    affects_modules=["grid_generator"],
                ),
                AssumptionRecord.quick(
                    id="channel_a_max_bay",
                    name="Maximum allowable bay size",
                    value=float(request.max_bay_mm),
                    unit="mm",
                    source=f"{self._SOURCE_MODULE}.grid_generator",
                    rationale=(
                        "Above this, an extra line is inserted.  Default "
                        f"{_DEFAULT_MAX_BAY_MM:.0f} mm is the practical upper "
                        "bound before pre/post-tensioning becomes mandatory."
                        if _is_default(request.max_bay_mm, _DEFAULT_MAX_BAY_MM)
                        else "User-supplied structural maximum."
                    ),
                    confidence=0.80
                    if _is_default(request.max_bay_mm, _DEFAULT_MAX_BAY_MM)
                    else 1.0,
                    overrideable=True,
                    affects_modules=["grid_generator"],
                ),
            ]
        )

    def record_building_code(self, request: StructuredInputRequest) -> None:
        value = request.building_code or _DEFAULT_BUILDING_CODE
        is_default = value == _DEFAULT_BUILDING_CODE
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_building_code",
                name="Governing building code",
                value=value,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Default IBC 2021; regional amendments are not yet applied."
                    if is_default
                    else "User-supplied governing code."
                ),
                confidence=0.70 if is_default else 1.0,
                overrideable=True,
                affects_modules=["phase3.load_combinations"],
            )
        )

    def record_roof_type(self, request: StructuredInputRequest) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_roof_type",
                name="Roof geometry type",
                value=request.roof_type.value,
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Flat-roof default (Phase 1 MVP assumes drain-to-interior)."
                    if request.roof_type.value == "FLAT"
                    else "User-supplied non-flat roof geometry."
                ),
                confidence=0.80 if request.roof_type.value == "FLAT" else 1.0,
                overrideable=True,
                affects_modules=["facade", "phase3.wind_loads"],
            )
        )

    # -- Derivations -------------------------------------------------------

    def record_perimeter_wall_thickness(
        self, thickness_mm: float, *, is_default: bool = True
    ) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_wall_thickness_perimeter",
                name="Perimeter (facade) wall thickness",
                value=float(thickness_mm),
                unit="mm",
                source=f"{self._SOURCE_MODULE}._generate_perimeter_walls",
                rationale=(
                    f"Default perimeter-wall thickness of {_DEFAULT_WALL_THICKNESS_MM:.0f}"
                    " mm for a typical RC exterior; refine per envelope spec."
                    if is_default
                    else "User-supplied perimeter-wall thickness."
                ),
                confidence=0.75 if is_default else 1.0,
                overrideable=True,
                affects_modules=["zone_classifier", "facade", "phase3.envelope"],
            )
        )

    def record_perimeter_wall_type(self, wall_type: str) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_wall_type_perimeter",
                name="Perimeter wall classification",
                value=wall_type,
                unit=None,
                source=f"{self._SOURCE_MODULE}._generate_perimeter_walls",
                rationale=(
                    "Perimeter walls assumed to be of type FACADE for a closed "
                    "rectangular footprint.  Interior partitions and shear "
                    "walls are not derived from structured form input."
                ),
                confidence=0.85,
                overrideable=True,
                affects_modules=["zone_classifier", "completeness_scorer"],
            )
        )

    def record_single_room_per_floor(self, num_stories: int) -> None:
        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_single_room_per_floor",
                name="Open-plan room-per-floor heuristic",
                value=True,
                unit=None,
                source=f"{self._SOURCE_MODULE}._generate_default_rooms",
                rationale=(
                    f"Structured input does not specify interior partitions; "
                    f"each of the {num_stories} floors is represented as one "
                    "open-plan zone covering the full footprint."
                ),
                confidence=0.60,
                overrideable=True,
                affects_modules=["completeness_scorer", "zone_classifier"],
            )
        )

    def record_input_source_immutable(self) -> None:
        """Marker assumption so the review UI can display the (non-overrideable)
        channel provenance alongside the overrideable defaults.
        """

        self._records.append(
            AssumptionRecord.quick(
                id="channel_a_input_source",
                name="Input channel",
                value="STRUCTURED_FORM",
                unit=None,
                source=self._SOURCE_MODULE,
                rationale=(
                    "Channel A marker; identifies that the graph was built from "
                    "a structured form submission rather than parsed CAD or a "
                    "CV pipeline output."
                ),
                confidence=1.0,
                overrideable=False,
                affects_modules=["provenance"],
            )
        )

    # -- Convenience bulk call --------------------------------------------

    def record_all_request_defaults(self, request: StructuredInputRequest) -> None:
        """Emit the full suite of form-sourced assumptions in one call."""

        self.record_input_source_immutable()
        self.record_floor_to_floor(request)
        self.record_ground_floor_height(request)
        self.record_bay_preferences(request)
        self.record_building_code(request)
        self.record_roof_type(request)


# ---------------------------------------------------------------------------
# Override helper
# ---------------------------------------------------------------------------


def apply_override(
    records: list[AssumptionRecord],
    *,
    assumption_id: str,
    value: object,
    source: str,
) -> Optional[AssumptionRecord]:
    """Mutate ``records`` in-place: mark the named assumption as overridden.

    Returns the updated :class:`AssumptionRecord` on success, or ``None`` when
    ``assumption_id`` is unknown.  Raises ``ValueError`` if the assumption is
    marked ``overrideable=False``.
    """

    for record in records:
        if record.id != assumption_id:
            continue
        if not record.overrideable:
            raise ValueError(
                f"Assumption {assumption_id!r} is flagged overrideable=False "
                "and cannot be modified via the review endpoint."
            )
        record.was_overridden = True
        record.override_value = value
        record.override_source = source
        return record
    return None


__all__ = [
    "StructuredInputAssumptionBuilder",
    "apply_override",
]
