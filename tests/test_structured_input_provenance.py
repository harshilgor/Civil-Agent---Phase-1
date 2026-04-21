"""Channel A — per-element provenance tests.

Every wall / room / column / core produced by the structured-form builder
must carry a :class:`ProvenanceRecord` with
``detector_source == DetectorSource.STRUCTURED_FORM`` and a ``run_id`` that
matches the rest of the graph's elements.
"""

from __future__ import annotations

from src.core.graph_builder import GraphBuilder
from src.schema.building_graph import Location
from src.schema.enums import DetectorSource, MaterialPreference, OccupancyType, RoofType
from src.schema.input_models import CorePlacement, StructuredInputRequest


def _request_with_cores() -> StructuredInputRequest:
    return StructuredInputRequest(
        project_name="Provenance Test Tower",
        location=Location(lat=40.7, lng=-74.0),
        length_mm=40000,
        width_mm=30000,
        num_stories=3,
        occupancy_type=OccupancyType.OFFICE,
        material_preference=MaterialPreference.REINFORCED_CONCRETE,
        roof_type=RoofType.FLAT,
        core_placements=[
            CorePlacement(
                x_start_mm=10000,
                y_start_mm=10000,
                x_end_mm=14000,
                y_end_mm=14000,
                contains_elevator=True,
                contains_stairs=True,
            )
        ],
    )


class TestChannelAProvenance:
    def test_walls_have_structured_form_provenance(self) -> None:
        graph = GraphBuilder().from_structured_input(_request_with_cores())
        assert graph.walls
        for wall in graph.walls:
            assert wall.provenance is not None
            assert wall.provenance.detector_source == DetectorSource.STRUCTURED_FORM

    def test_rooms_have_structured_form_provenance(self) -> None:
        graph = GraphBuilder().from_structured_input(_request_with_cores())
        assert graph.rooms
        for room in graph.rooms:
            assert room.provenance is not None
            assert room.provenance.detector_source == DetectorSource.STRUCTURED_FORM

    def test_columns_have_structured_form_provenance(self) -> None:
        graph = GraphBuilder().from_structured_input(_request_with_cores())
        assert graph.column_candidates
        for column in graph.column_candidates:
            assert column.provenance is not None
            assert column.provenance.detector_source == DetectorSource.STRUCTURED_FORM

    def test_cores_have_structured_form_provenance(self) -> None:
        graph = GraphBuilder().from_structured_input(_request_with_cores())
        assert graph.cores
        for core in graph.cores:
            assert core.provenance is not None
            assert core.provenance.detector_source == DetectorSource.STRUCTURED_FORM

    def test_run_id_is_consistent_across_all_elements(self) -> None:
        graph = GraphBuilder().from_structured_input(
            _request_with_cores(), run_id="pinned-run-id-123"
        )
        all_elements = (
            list(graph.walls)
            + list(graph.rooms)
            + list(graph.column_candidates)
            + list(graph.cores)
        )
        run_ids = {e.provenance.run_id for e in all_elements if e.provenance}
        assert run_ids == {"pinned-run-id-123"}

    def test_explicit_run_id_is_honored(self) -> None:
        graph = GraphBuilder().from_structured_input(
            _request_with_cores(), run_id="explicit-run-id"
        )
        assert graph.walls[0].provenance.run_id == "explicit-run-id"

    def test_job_id_defaults_to_run_id_when_unspecified(self) -> None:
        graph = GraphBuilder().from_structured_input(
            _request_with_cores(), run_id="shared-id"
        )
        assert graph.metadata.job_id == "shared-id"

    def test_job_id_separately_settable(self) -> None:
        graph = GraphBuilder().from_structured_input(
            _request_with_cores(), run_id="run-xyz", job_id="job-abc"
        )
        assert graph.metadata.job_id == "job-abc"
        assert graph.walls[0].provenance.run_id == "run-xyz"

    def test_confidence_from_model_is_one_for_user_verified_input(self) -> None:
        graph = GraphBuilder().from_structured_input(_request_with_cores())
        assert graph.walls[0].provenance.confidence_from_model == 1.0

    def test_no_ml_model_id_is_recorded(self) -> None:
        """Channel A never invokes an ML model; model_id / version / hash stay None."""

        graph = GraphBuilder().from_structured_input(_request_with_cores())
        for wall in graph.walls:
            assert wall.provenance.model_id is None
            assert wall.provenance.model_version is None
            assert wall.provenance.weights_manifest_hash is None
