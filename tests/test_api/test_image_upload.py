"""Tests for the async image upload endpoint (Step 5).

Channel C submits a synthetic Celery task that completes eagerly under the
session-scoped ``task_always_eager`` fixture in :mod:`tests.conftest`, so
these tests exercise the full `202 + job_id` → `GET /status` →
``completed`` + ``building_graph`` round-trip without needing a live
Redis broker.  The earlier ``@pytest.mark.requires_redis`` markers on
this module are gone for that reason; the stub fallback still kicks in
if Celery ever fails to enqueue, so the contract is resilient to an
outage.
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
    assert body["status"] in {"queued", "processing", "completed"}
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


def test_eager_run_produces_building_graph(client: TestClient) -> None:
    """Eager-mode Celery should hand back a full graph on the first poll.

    The test fixture is a 16x16 blank PNG and CI has no ML weights, so
    Channel C's Stage 3-9 pipeline produces nothing to vectorise.  The
    builder degrades gracefully to a placeholder graph — schema-valid,
    marked with ``channel_c_degraded_placeholder`` so the review UI
    will flag it for human triage.  The happy-path (real walls, real
    building graph) is exercised in
    ``tests/test_core/test_image_graph_builder.py`` with an injected
    fake ML engine.
    """

    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    post = client.post("/api/v1/building/upload/image", files=files)
    assert post.status_code == 202
    job_id = post.json()["job_id"]

    status = client.get(f"/api/v1/building/upload/image/{job_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["progress_percent"] == 100
    assert body["result_id"] == job_id
    assert body["error"] is None
    assert body["building_graph"] is not None
    bg = body["building_graph"]
    assert bg["metadata"]["input_source"] == "FLOOR_PLAN_IMAGE"
    # Degraded placeholder: schema is still valid (one story, a
    # synthetic single-room polygon), but the degradation is
    # surfaced loudly on the assumption register.
    register_ids = {a["id"] for a in bg["metadata"]["assumption_register"]}
    if not bg["walls"]:
        assert "channel_c_degraded_placeholder" in register_ids
        assert "image_pipeline_produced_no_walls" in bg["metadata"]["warnings"]
    assert len(bg["stories"]) >= 1
    assert bg["facade"]["perimeter_length_mm"] > 0
