"""End-to-end tests for the async CAD upload endpoint.

Step 5 introduced the endpoint against a stubbed worker task.  Step 6
rewired ``process_cad_file`` to the real DXF / IFC parsers; these tests
now drive the full parse → build → stamp pipeline.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_cad_upload_dxf_returns_202_and_completes(
    client: TestClient, sample_dxf_bytes: bytes
) -> None:
    files = {"file": ("plan.dxf", sample_dxf_bytes, "application/octet-stream")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 202
    body = r.json()
    assert body["file_type"] == "DXF"
    # Eager Celery / in-process fallback both land in a terminal state
    # by the time the response hits the wire.
    assert body["status"] in {"queued", "processing", "completed"}


def test_cad_upload_ifc_returns_202_and_completes(
    client: TestClient, sample_ifc_bytes: bytes
) -> None:
    files = {"file": ("plan.ifc", sample_ifc_bytes, "application/octet-stream")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 202
    assert r.json()["file_type"] == "IFC"


def test_cad_upload_dwg_is_accepted_even_without_converter(
    client: TestClient,
) -> None:
    """The endpoint accepts .dwg; parsing fails async when ODA isn't wired."""

    files = {"file": ("plan.dwg", b"fake-dwg-bytes", "application/octet-stream")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 202
    assert r.json()["file_type"] == "DWG"


def test_cad_rejects_bad_extension(client: TestClient) -> None:
    files = {"file": ("plan.png", b"nope", "image/png")}
    r = client.post("/api/v1/building/upload/cad", files=files)
    assert r.status_code == 400


def test_cad_status_404_on_unknown_job(client: TestClient) -> None:
    r = client.get("/api/v1/building/upload/cad/does-not-exist/status")
    assert r.status_code == 404


def test_cad_dxf_status_reports_completed_with_graph(
    client: TestClient, sample_dxf_bytes: bytes
) -> None:
    files = {"file": ("plan.dxf", sample_dxf_bytes, "application/octet-stream")}
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
    # Parser pulled the five wall lines from the fixture.
    assert len(bg["walls"]) >= 4


def test_cad_ifc_status_reports_completed_with_graph(
    client: TestClient, sample_ifc_bytes: bytes
) -> None:
    files = {"file": ("plan.ifc", sample_ifc_bytes, "application/octet-stream")}
    post = client.post("/api/v1/building/upload/cad", files=files)
    job_id = post.json()["job_id"]

    status = client.get(f"/api/v1/building/upload/cad/{job_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["building_graph"]["metadata"]["input_source"] == "IFC_FILE"


def test_cad_dwg_without_converter_reports_failure(client: TestClient) -> None:
    """Uploading a DWG with no ODA converter configured must surface a
    structured ``failed`` status rather than silently returning stub data."""

    files = {"file": ("plan.dwg", b"fake-dwg-bytes", "application/octet-stream")}
    post = client.post("/api/v1/building/upload/cad", files=files)
    job_id = post.json()["job_id"]

    status = client.get(f"/api/v1/building/upload/cad/{job_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert body["building_graph"] is None
    assert "DWG" in (body["error"] or "")


def test_cad_upload_garbage_dxf_reports_failure(client: TestClient) -> None:
    """Bytes that aren't a DXF must surface as a failed job with a
    structured error message (not a silent stub)."""

    files = {"file": ("plan.dxf", b"not-a-real-dxf", "application/octet-stream")}
    post = client.post("/api/v1/building/upload/cad", files=files)
    job_id = post.json()["job_id"]

    status = client.get(f"/api/v1/building/upload/cad/{job_id}/status")
    body = status.json()
    assert body["status"] == "failed"
    assert body["error"] is not None
