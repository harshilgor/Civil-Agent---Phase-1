"""Tests for the async CAD upload endpoint (Step 5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        ("plan.dxf", "DXF"),
        ("plan.dwg", "DWG"),
        ("plan.ifc", "IFC"),
    ],
)
def test_cad_upload_returns_202_with_job_id(
    client: TestClient, filename: str, expected_type: str
) -> None:
    files = {"file": (filename, b"fake-cad-bytes", "application/octet-stream")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["filename"] == filename
    assert body["file_type"] == expected_type
    assert body["status"] in {"queued", "processing", "completed"}


def test_cad_rejects_bad_extension(client: TestClient) -> None:
    files = {"file": ("plan.png", b"nope", "image/png")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 400


def test_cad_status_404_on_unknown_job(client: TestClient) -> None:
    r = client.get("/api/v1/building/upload/cad/does-not-exist/status")
    assert r.status_code == 404


def test_cad_status_returns_completed_with_graph(client: TestClient) -> None:
    files = {"file": ("plan.dxf", b"fake-cad-bytes", "application/octet-stream")}
    post = client.post("/api/v1/building/upload/cad", files=files)
    job_id = post.json()["job_id"]

    status = client.get(f"/api/v1/building/upload/cad/{job_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["progress_percent"] == 100
    assert body["error"] is None
    bg = body["building_graph"]
    assert bg is not None
    assert bg["metadata"]["input_source"] == "DXF_FILE"
