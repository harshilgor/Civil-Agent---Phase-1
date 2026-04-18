"""Tests for the async image upload endpoint (Gap 7 integration).

These tests exercise the API surface without requiring a live Redis broker —
the Celery enqueue failure path is tolerated and the job remains in ``queued``
state.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _tiny_png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_accepts_png_and_returns_job_id(client: TestClient) -> None:
    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    r = client.post("/api/v1/building/upload/image", files=files)
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] in {"queued", "processing"}
    assert body["filename"] == "plan.png"


def test_status_endpoint_roundtrip(client: TestClient) -> None:
    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    r = client.post("/api/v1/building/upload/image", files=files)
    job_id = r.json()["job_id"]
    r2 = client.get(f"/api/v1/building/upload/image/{job_id}/status")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id
    assert body["status"] in {"queued", "processing", "completed", "failed"}


def test_upload_rejects_bad_extension(client: TestClient) -> None:
    files = {"file": ("plan.exe", b"nope", "application/octet-stream")}
    r = client.post("/api/v1/building/upload/image", files=files)
    assert r.status_code == 400


def test_status_404_on_unknown_job(client: TestClient) -> None:
    r = client.get("/api/v1/building/upload/image/not-a-job/status")
    assert r.status_code == 404
