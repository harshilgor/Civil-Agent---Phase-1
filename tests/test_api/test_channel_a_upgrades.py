"""API tests for the Step-4 Channel A upgrades and the unified jobs endpoint.

Complements ``tests/test_api/test_structured_input.py`` (baseline Channel A
surface) with the provenance / assumption_register / override / jobs
endpoints introduced in Step 4.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def valid_payload() -> dict:
    return {
        "project_name": "Step 4 Tower",
        "location": {"lat": 40.7, "lng": -74.0, "city": "NYC", "state": "NY", "country": "US"},
        "length_mm": 40000,
        "width_mm": 30000,
        "num_stories": 4,
        "floor_to_floor_mm": 3900,
        "occupancy_type": "OFFICE",
        "material_preference": "REINFORCED_CONCRETE",
        "preferred_bay_x_mm": 8000,
        "preferred_bay_y_mm": 8000,
    }


def _create(client: TestClient, payload: dict) -> dict:
    resp = client.post("/api/v1/building/structured", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# assumption_register visible in the response
# ---------------------------------------------------------------------------


class TestAssumptionRegisterInResponse:
    def test_register_is_list(self, client: TestClient, valid_payload: dict):
        body = _create(client, valid_payload)
        register = body["building_graph"]["metadata"]["assumption_register"]
        assert isinstance(register, list)
        assert len(register) > 0

    def test_every_record_has_required_fields(self, client: TestClient, valid_payload: dict):
        register = _create(client, valid_payload)["building_graph"]["metadata"][
            "assumption_register"
        ]
        required = {"id", "value", "unit", "source", "confidence", "rationale", "overrideable"}
        for record in register:
            assert required.issubset(record.keys()), (
                f"Missing keys in record {record!r}: "
                f"{required - record.keys()}"
            )

    def test_input_source_marker_present(self, client: TestClient, valid_payload: dict):
        register = _create(client, valid_payload)["building_graph"]["metadata"][
            "assumption_register"
        ]
        ids = [r["id"] for r in register]
        assert "channel_a_input_source" in ids

    def test_inferred_building_type_set(self, client: TestClient, valid_payload: dict):
        meta = _create(client, valid_payload)["building_graph"]["metadata"]
        assert meta["inferred_building_type"] == "COMMERCIAL"  # OFFICE → COMMERCIAL

    def test_job_id_set(self, client: TestClient, valid_payload: dict):
        meta = _create(client, valid_payload)["building_graph"]["metadata"]
        assert meta["job_id"]
        assert isinstance(meta["job_id"], str) and len(meta["job_id"]) > 0

    def test_completeness_score_populated(self, client: TestClient, valid_payload: dict):
        meta = _create(client, valid_payload)["building_graph"]["metadata"]
        comp = meta["completeness"]
        assert comp is not None
        for axis in ("overall", "geometry", "semantics", "detector_coverage"):
            assert 0.0 <= comp[axis] <= 1.0


# ---------------------------------------------------------------------------
# per-element provenance in response
# ---------------------------------------------------------------------------


class TestProvenanceInResponse:
    def test_walls_carry_provenance(self, client: TestClient, valid_payload: dict):
        walls = _create(client, valid_payload)["building_graph"]["walls"]
        assert walls
        for wall in walls:
            prov = wall["provenance"]
            assert prov is not None
            assert prov["detector_source"] == "STRUCTURED_FORM"
            assert prov["run_id"]

    def test_rooms_carry_provenance(self, client: TestClient, valid_payload: dict):
        rooms = _create(client, valid_payload)["building_graph"]["rooms"]
        for room in rooms:
            assert room["provenance"]["detector_source"] == "STRUCTURED_FORM"

    def test_columns_carry_provenance(self, client: TestClient, valid_payload: dict):
        cols = _create(client, valid_payload)["building_graph"]["column_candidates"]
        for col in cols:
            assert col["provenance"]["detector_source"] == "STRUCTURED_FORM"


# ---------------------------------------------------------------------------
# Override endpoint
# ---------------------------------------------------------------------------


class TestOverrideEndpoint:
    def test_happy_path_marks_overridden(self, client: TestClient, valid_payload: dict):
        body = _create(client, valid_payload)
        project_id = body["project_id"]
        resp = client.post(
            f"/api/v1/building/{project_id}/assumptions/channel_a_preferred_bay_x/override",
            json={"value": 9000, "source": "reviewer:alice"},
        )
        assert resp.status_code == 200, resp.text
        register = resp.json()["building_graph"]["metadata"]["assumption_register"]
        bay_x = next(r for r in register if r["id"] == "channel_a_preferred_bay_x")
        assert bay_x["was_overridden"] is True
        assert bay_x["override_value"] == 9000
        assert bay_x["override_source"] == "reviewer:alice"

    def test_unknown_project_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/building/no-such-project/assumptions/channel_a_preferred_bay_x/override",
            json={"value": 9000, "source": "x"},
        )
        assert resp.status_code == 404

    def test_unknown_assumption_returns_404(
        self, client: TestClient, valid_payload: dict
    ):
        project_id = _create(client, valid_payload)["project_id"]
        resp = client.post(
            f"/api/v1/building/{project_id}/assumptions/does_not_exist/override",
            json={"value": 1, "source": "x"},
        )
        assert resp.status_code == 404

    def test_non_overrideable_returns_422(
        self, client: TestClient, valid_payload: dict
    ):
        project_id = _create(client, valid_payload)["project_id"]
        resp = client.post(
            f"/api/v1/building/{project_id}/assumptions/channel_a_input_source/override",
            json={"value": "CAD_DIRECT", "source": "x"},
        )
        assert resp.status_code == 422

    def test_missing_source_returns_422(
        self, client: TestClient, valid_payload: dict
    ):
        project_id = _create(client, valid_payload)["project_id"]
        resp = client.post(
            f"/api/v1/building/{project_id}/assumptions/channel_a_preferred_bay_x/override",
            json={"value": 9000},  # missing source
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Jobs endpoint
# ---------------------------------------------------------------------------


class TestJobsEndpoint:
    def test_job_lookup_returns_completed_status(
        self, client: TestClient, valid_payload: dict
    ):
        body = _create(client, valid_payload)
        job_id = body["building_graph"]["metadata"]["job_id"]

        resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
        assert data["progress_percent"] == 100.0
        assert data["result_id"] == body["project_id"]
        assert data["building_graph"]["metadata"]["job_id"] == job_id

    def test_unknown_job_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/jobs/nonexistent-job-id")
        assert resp.status_code == 404

    def test_review_applies_overrides(self, client: TestClient, valid_payload: dict):
        body = _create(client, valid_payload)
        job_id = body["building_graph"]["metadata"]["job_id"]

        review_resp = client.post(
            f"/api/v1/jobs/{job_id}/review",
            json={
                "overrides": [
                    {
                        "assumption_id": "channel_a_preferred_bay_x",
                        "value": 10000,
                        "source": "reviewer",
                    },
                    {
                        "assumption_id": "channel_a_preferred_bay_y",
                        "value": 9000,
                        "source": "reviewer",
                    },
                ],
                "reviewer": "jdoe",
            },
        )
        assert review_resp.status_code == 200, review_resp.text
        register = review_resp.json()["building_graph"]["metadata"]["assumption_register"]
        bay_x = next(r for r in register if r["id"] == "channel_a_preferred_bay_x")
        bay_y = next(r for r in register if r["id"] == "channel_a_preferred_bay_y")
        assert bay_x["was_overridden"] and bay_y["was_overridden"]
        assert bay_x["override_source"].endswith(":jdoe")

    def test_review_rejects_unknown_assumption(
        self, client: TestClient, valid_payload: dict
    ):
        job_id = _create(client, valid_payload)["building_graph"]["metadata"]["job_id"]
        resp = client.post(
            f"/api/v1/jobs/{job_id}/review",
            json={
                "overrides": [
                    {"assumption_id": "nope", "value": 1, "source": "x"},
                ]
            },
        )
        assert resp.status_code == 404

    def test_review_requires_non_empty_overrides(
        self, client: TestClient, valid_payload: dict
    ):
        job_id = _create(client, valid_payload)["building_graph"]["metadata"]["job_id"]
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json={"overrides": []})
        assert resp.status_code == 422

    def test_review_on_unknown_job_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/jobs/no-such-job/review",
            json={"overrides": [{"assumption_id": "x", "value": 1, "source": "y"}]},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete cleans up job index
# ---------------------------------------------------------------------------


class TestDeleteClearsJobIndex:
    def test_delete_project_removes_job(
        self, client: TestClient, valid_payload: dict
    ):
        body = _create(client, valid_payload)
        project_id = body["project_id"]
        job_id = body["building_graph"]["metadata"]["job_id"]

        assert client.delete(f"/api/v1/building/{project_id}").status_code == 204
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
