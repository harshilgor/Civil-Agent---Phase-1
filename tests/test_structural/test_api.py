"""Integration tests for the Phase 2 API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import create_app


def test_structural_endpoint_full_flow(sample_structured_request):
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/building/structured",
            json=sample_structured_request.model_dump(mode="json"),
        )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["project_id"]

        # POST /structural to build the design graph
        post = client.post(f"/api/v1/building/{project_id}/structural")
        assert post.status_code == 201, post.text
        sdg = post.json()
        assert "zones" in sdg
        assert "support_candidates" in sdg
        assert "constraints" in sdg

        # GET retrieves the same payload
        get = client.get(f"/api/v1/building/{project_id}/structural")
        assert get.status_code == 200

        # Summary endpoint returns compact data
        summary = client.get(f"/api/v1/building/{project_id}/structural/summary")
        assert summary.status_code == 200
        body = summary.json()
        assert "zone_count" in body
        assert "gravity_system_candidates" in body


def test_structural_endpoint_404_for_unknown():
    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/api/v1/building/does-not-exist/structural")
        assert resp.status_code == 404


def test_structural_get_before_post_is_404(sample_structured_request):
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/building/structured",
            json=sample_structured_request.model_dump(mode="json"),
        )
        project_id = resp.json()["project_id"]
        get = client.get(f"/api/v1/building/{project_id}/structural")
        assert get.status_code == 404
