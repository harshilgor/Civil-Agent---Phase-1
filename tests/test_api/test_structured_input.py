"""API tests for the structured input (Channel A) endpoints."""

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
        "project_name": "API Test Tower",
        "location": {
            "lat": 37.77,
            "lng": -122.42,
            "city": "San Francisco",
            "state": "CA",
            "country": "US",
        },
        "length_mm": 32000,
        "width_mm": 24000,
        "num_stories": 5,
        "floor_to_floor_mm": 3600,
        "ground_floor_height_mm": 4500,
        "occupancy_type": "OFFICE",
        "material_preference": "REINFORCED_CONCRETE",
        "preferred_bay_x_mm": 8000,
        "preferred_bay_y_mm": 8000,
    }


class TestCreateBuilding:
    def test_create_returns_201(self, client: TestClient, valid_payload: dict):
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        assert resp.status_code == 201

    def test_response_has_project_id(self, client: TestClient, valid_payload: dict):
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        data = resp.json()
        assert "project_id" in data
        assert len(data["project_id"]) > 0

    def test_building_graph_in_response(self, client: TestClient, valid_payload: dict):
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        data = resp.json()
        bg = data["building_graph"]
        assert bg["project"]["name"] == "API Test Tower"
        assert bg["project"]["num_stories"] == 5
        assert len(bg["stories"]) == 5
        assert len(bg["walls"]) == 4
        assert len(bg["grid"]["x_lines"]) >= 2
        assert len(bg["column_candidates"]) > 0

    def test_grid_has_correct_structure(self, client: TestClient, valid_payload: dict):
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        grid = resp.json()["building_graph"]["grid"]
        assert "x_lines" in grid
        assert "y_lines" in grid
        assert "bays" in grid
        for bay in grid["bays"]:
            assert bay["span_x_mm"] > 0
            assert bay["span_y_mm"] > 0

    def test_metadata_is_structured_form(self, client: TestClient, valid_payload: dict):
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        meta = resp.json()["building_graph"]["metadata"]
        assert meta["input_source"] == "STRUCTURED_FORM"
        assert meta["confidence_scores"]["overall"] >= 0.85
        assert len(meta["assumptions_made"]) > 0


class TestCreateValidation:
    def test_missing_project_name_returns_422(self, client: TestClient, valid_payload: dict):
        del valid_payload["project_name"]
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        assert resp.status_code == 422

    def test_zero_stories_returns_422(self, client: TestClient, valid_payload: dict):
        valid_payload["num_stories"] = 0
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        assert resp.status_code == 422

    def test_negative_length_returns_422(self, client: TestClient, valid_payload: dict):
        valid_payload["length_mm"] = -1000
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        assert resp.status_code == 422

    def test_invalid_occupancy_returns_422(self, client: TestClient, valid_payload: dict):
        valid_payload["occupancy_type"] = "SPACESHIP"
        resp = client.post("/api/v1/building/structured", json=valid_payload)
        assert resp.status_code == 422


class TestGetBuilding:
    def test_get_existing_project(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]

        get_resp = client.get(f"/api/v1/building/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["project_id"] == project_id

    def test_get_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/building/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateGrid:
    def test_update_grid_returns_200(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]

        update_resp = client.put(
            f"/api/v1/building/{project_id}/grid",
            json={"preferred_bay_x_mm": 10000, "preferred_bay_y_mm": 10000},
        )
        assert update_resp.status_code == 200

    def test_update_grid_changes_bays(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]
        original_bays = len(create_resp.json()["building_graph"]["grid"]["bays"])

        update_resp = client.put(
            f"/api/v1/building/{project_id}/grid",
            json={"preferred_bay_x_mm": 16000, "preferred_bay_y_mm": 12000},
        )
        new_bays = len(update_resp.json()["building_graph"]["grid"]["bays"])
        assert new_bays != original_bays


class TestDeleteBuilding:
    def test_delete_returns_204(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]

        del_resp = client.delete(f"/api/v1/building/{project_id}")
        assert del_resp.status_code == 204

    def test_delete_then_get_returns_404(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]
        client.delete(f"/api/v1/building/{project_id}")

        get_resp = client.get(f"/api/v1/building/{project_id}")
        assert get_resp.status_code == 404


class TestExport:
    def test_export_json(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]

        export_resp = client.get(f"/api/v1/building/{project_id}/export?format=json")
        assert export_resp.status_code == 200
        data = export_resp.json()
        assert "project" in data
        assert "stories" in data

    def test_export_geojson_returns_501(self, client: TestClient, valid_payload: dict):
        create_resp = client.post("/api/v1/building/structured", json=valid_payload)
        project_id = create_resp.json()["project_id"]

        resp = client.get(f"/api/v1/building/{project_id}/export?format=geojson")
        assert resp.status_code == 501


class TestHealthCheck:
    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
