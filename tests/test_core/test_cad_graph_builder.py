"""Unit tests for :mod:`src.core.cad_graph_builder`.

These tests drive :class:`CadGraphBuilder.build` with *synthetic*
parser output (dicts shaped like the real DXF / IFC parser payload)
so we can isolate the orchestration layer from the parsers.
"""

from __future__ import annotations

import pytest

from src.core.cad_graph_builder import CadGraphBuilder
from src.schema.enums import (
    DetectorSource,
    InputSource,
    MaterialPreference,
    OccupancyType,
)


def _minimal_dxf_parsed() -> dict:
    """Return a dict shaped like ``DXFParser.parse`` output.

    The fixture is a 10×8 m shoebox with four walls and a grid. No rooms,
    no openings — minimal enough to cover the common case without
    incidentally testing DXF-specific parser behaviour.
    """

    return {
        "units": "mm",
        "walls": [
            {"start": [0, 0], "end": [10000, 0], "thickness_mm": 200},
            {"start": [10000, 0], "end": [10000, 8000], "thickness_mm": 200},
            {"start": [10000, 8000], "end": [0, 8000], "thickness_mm": 200},
            {"start": [0, 8000], "end": [0, 0], "thickness_mm": 200},
        ],
        "grid_lines": {
            "x_lines": [{"position_mm": 0.0}, {"position_mm": 10000.0}],
            "y_lines": [{"position_mm": 0.0}, {"position_mm": 8000.0}],
        },
        "rooms": [],
        "text_annotations": [],
        "doors": [],
        "windows": [],
    }


class TestBuildHappyPath:
    def test_dxf_minimal_produces_graph(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(),
            input_source=InputSource.DXF_FILE,
            project_name="Shoebox",
        )
        assert bg.project.name == "Shoebox"
        assert bg.metadata.input_source == InputSource.DXF_FILE
        assert len(bg.walls) >= 3
        assert len(bg.stories) == 1

    def test_all_walls_are_stamped_with_cad_direct(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        for w in bg.walls:
            assert w.provenance is not None
            assert w.provenance.detector_source == DetectorSource.CAD_DIRECT

    def test_ifc_input_stamps_ifc_direct(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(),
            input_source=InputSource.IFC_FILE,
        )
        for w in bg.walls:
            assert w.provenance.detector_source == DetectorSource.IFC_DIRECT

    def test_job_id_stamped_into_metadata(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(),
            input_source=InputSource.DXF_FILE,
            job_id="job-abc",
        )
        assert bg.metadata.job_id == "job-abc"


class TestInputSourceGuard:
    def test_rejects_structured_form(self) -> None:
        with pytest.raises(ValueError):
            CadGraphBuilder().build(
                _minimal_dxf_parsed(),
                input_source=InputSource.STRUCTURED_FORM,
            )

    def test_rejects_floor_plan_image(self) -> None:
        with pytest.raises(ValueError):
            CadGraphBuilder().build(
                _minimal_dxf_parsed(),
                input_source=InputSource.FLOOR_PLAN_IMAGE,
            )


class TestAssumptionRegister:
    def test_register_includes_input_source_marker(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        ids = {a.id for a in bg.metadata.assumption_register}
        assert "channel_b_input_source" in ids
        assert "channel_b_unit_conversion" in ids

    def test_register_includes_occupancy_and_material(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(),
            input_source=InputSource.DXF_FILE,
            occupancy_type=OccupancyType.RESIDENTIAL,
            material_preference=MaterialPreference.STRUCTURAL_STEEL,
        )
        register = {a.id: a for a in bg.metadata.assumption_register}
        assert register["channel_b_occupancy_type"].value == "RESIDENTIAL"
        assert (
            register["channel_b_material_preference"].value == "STRUCTURAL_STEEL"
        )


class TestCompletenessIsUserAuthoritative:
    def test_cad_input_has_no_missing_subsystems(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        assert bg.metadata.completeness is not None
        assert bg.metadata.completeness.missing_subsystems == []

    def test_cad_detector_coverage_is_one(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        assert bg.metadata.completeness.detector_coverage == pytest.approx(1.0)


class TestGridInferenceAssumption:
    def test_no_grid_triggers_inferred_from_walls_record(self) -> None:
        parsed = _minimal_dxf_parsed()
        parsed["grid_lines"] = {"x_lines": [], "y_lines": []}
        bg = CadGraphBuilder().build(
            parsed, input_source=InputSource.DXF_FILE
        )
        ids = {a.id for a in bg.metadata.assumption_register}
        assert "channel_b_grid_inferred_from_walls" in ids

    def test_explicit_grid_does_not_trigger_inference(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        ids = {a.id for a in bg.metadata.assumption_register}
        assert "channel_b_grid_inferred_from_walls" not in ids


class TestNumStoriesOverride:
    def test_override_takes_effect(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(),
            input_source=InputSource.DXF_FILE,
            num_stories=3,
        )
        assert len(bg.stories) == 3

    def test_default_is_one_story(self) -> None:
        bg = CadGraphBuilder().build(
            _minimal_dxf_parsed(), input_source=InputSource.DXF_FILE
        )
        assert len(bg.stories) == 1
