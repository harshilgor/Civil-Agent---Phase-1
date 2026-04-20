"""Unit tests for :mod:`src.core.cad_assumption_builder`.

The Channel B assumption builder mirrors the Channel A contract: every
``record_*`` call has to emit an :class:`AssumptionRecord` with a
deterministic id, a sensible confidence band, and the ``overrideable``
flag that the review UI surfaces.
"""

from __future__ import annotations

import pytest

from src.core.cad_assumption_builder import CadAssumptionBuilder
from src.schema.enums import InputSource, MaterialPreference, OccupancyType


@pytest.fixture()
def dxf_builder() -> CadAssumptionBuilder:
    return CadAssumptionBuilder(input_source=InputSource.DXF_FILE)


@pytest.fixture()
def ifc_builder() -> CadAssumptionBuilder:
    return CadAssumptionBuilder(input_source=InputSource.IFC_FILE)


class TestInputSourceMarker:
    def test_pins_channel_as_immutable(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_input_source_immutable()
        records = dxf_builder.records
        assert len(records) == 1
        r = records[0]
        assert r.id == "channel_b_input_source"
        assert r.value == "DXF_FILE"
        assert r.overrideable is False
        assert r.confidence == 1.0


class TestUnitConversion:
    def test_mm_source_marks_no_conversion(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_unit_conversion("mm")
        r = dxf_builder.records[0]
        assert "no conversion" in r.rationale.lower()
        assert r.overrideable is False

    def test_inch_source_marks_conversion(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_unit_conversion("in")
        r = dxf_builder.records[0]
        assert "millimetres" in r.rationale.lower()


class TestLayerConventions:
    def test_dxf_records_layer_convention(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_layer_conventions(
            wall_hits=5, grid_hits=2, room_hits=3
        )
        r = dxf_builder.records[0]
        assert r.id == "channel_b_layer_conventions"
        assert r.value == {
            "wall_layers_matched": 5,
            "grid_layers_matched": 2,
            "room_layers_matched": 3,
        }

    def test_ifc_skips_layer_convention(
        self, ifc_builder: CadAssumptionBuilder
    ) -> None:
        ifc_builder.record_layer_conventions(
            wall_hits=5, grid_hits=2, room_hits=3
        )
        assert ifc_builder.records == []


class TestWallThickness:
    def test_default_thickness_lowers_confidence(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_default_wall_thickness(200.0, used_default=True)
        r = dxf_builder.records[0]
        assert r.value == 200.0
        assert r.unit == "mm"
        assert r.confidence == pytest.approx(0.70)
        assert r.overrideable is True

    def test_measured_thickness_is_high_confidence(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_default_wall_thickness(300.0, used_default=False)
        assert dxf_builder.records[0].confidence == 1.0


class TestOpeningSnapping:
    def test_skips_when_no_openings(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_opening_wall_association(total=0, snapped=0)
        assert dxf_builder.records == []

    def test_records_snap_totals(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_opening_wall_association(total=4, snapped=3)
        r = dxf_builder.records[0]
        assert r.value == {"total_openings": 4, "snapped_to_nearest_wall": 3}


class TestProgramFallbacks:
    def test_default_occupancy_lower_confidence(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_occupancy_fallback(
            OccupancyType.OFFICE, was_inferred=False
        )
        assert dxf_builder.records[0].confidence == pytest.approx(0.55)

    def test_inferred_occupancy_higher_confidence(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_occupancy_fallback(
            OccupancyType.OFFICE, was_inferred=True
        )
        assert dxf_builder.records[0].confidence == pytest.approx(0.80)

    def test_material_default_vs_inferred(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_material_fallback(
            MaterialPreference.REINFORCED_CONCRETE, was_inferred=False
        )
        dxf_builder.record_material_fallback(
            MaterialPreference.STRUCTURAL_STEEL, was_inferred=True
        )
        assert dxf_builder.records[0].confidence == pytest.approx(0.55)
        assert dxf_builder.records[1].confidence == pytest.approx(0.80)


class TestStoriesAndHeights:
    def test_num_stories_default_marked(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_num_stories_fallback(1, source="default")
        r = dxf_builder.records[0]
        assert r.value == 1
        assert r.confidence == pytest.approx(0.50)

    def test_num_stories_from_ifc_high_confidence(
        self, ifc_builder: CadAssumptionBuilder
    ) -> None:
        ifc_builder.record_num_stories_fallback(3, source="ifc_building_storey")
        r = ifc_builder.records[0]
        assert r.value == 3
        assert r.confidence == pytest.approx(0.90)

    def test_f2f_default_vs_derived(
        self, ifc_builder: CadAssumptionBuilder
    ) -> None:
        ifc_builder.record_f2f_fallback(3900.0, used_default=True)
        ifc_builder.record_f2f_fallback(3500.0, used_default=False)
        assert ifc_builder.records[0].confidence == pytest.approx(0.70)
        assert ifc_builder.records[1].confidence == pytest.approx(0.95)


class TestGeometryFallbacks:
    def test_location_is_overrideable(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_location_fallback()
        r = dxf_builder.records[0]
        assert r.value == {"lat": 0.0, "lng": 0.0}
        assert r.overrideable is True

    def test_grid_inferred_from_walls_records(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_grid_inferred_from_walls()
        assert dxf_builder.records[0].value is True

    def test_synthesised_room_polygons_skip_when_zero(
        self, ifc_builder: CadAssumptionBuilder
    ) -> None:
        ifc_builder.record_room_polygon_synthesised(count=0)
        assert ifc_builder.records == []

    def test_synthesised_room_polygons_record_count(
        self, ifc_builder: CadAssumptionBuilder
    ) -> None:
        ifc_builder.record_room_polygon_synthesised(count=7)
        assert ifc_builder.records[0].value == 7

    def test_column_layer_skips_when_zero(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_column_layer_found(count=0)
        assert dxf_builder.records == []

    def test_column_layer_records_count(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_column_layer_found(count=6)
        assert dxf_builder.records[0].value == 6


class TestBuildingCodeDefault:
    def test_emits_ibc_2021(self, dxf_builder: CadAssumptionBuilder) -> None:
        dxf_builder.record_building_code_default()
        r = dxf_builder.records[0]
        assert r.value == "IBC 2021"
        assert r.overrideable is True


class TestBuilderIntegration:
    def test_records_are_accumulated_in_order(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_input_source_immutable()
        dxf_builder.record_unit_conversion("mm")
        dxf_builder.record_default_wall_thickness(200.0, used_default=True)
        ids = [r.id for r in dxf_builder.records]
        assert ids == [
            "channel_b_input_source",
            "channel_b_unit_conversion",
            "channel_b_wall_thickness_default",
        ]

    def test_records_property_returns_copy(
        self, dxf_builder: CadAssumptionBuilder
    ) -> None:
        dxf_builder.record_input_source_immutable()
        snapshot = dxf_builder.records
        snapshot.clear()
        # Mutating the returned list must not empty the builder's state.
        assert len(dxf_builder.records) == 1
