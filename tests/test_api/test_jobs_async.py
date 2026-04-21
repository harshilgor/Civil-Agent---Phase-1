"""Unified /api/v1/jobs/{job_id} endpoint over Channels B / C (Step 5)."""

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


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_jobs_endpoint_resolves_channel_c_image_job(client: TestClient) -> None:
    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    post = client.post("/api/v1/building/upload/image", files=files)
    job_id = post.json()["job_id"]

    r = client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "completed"
    assert body["result_id"] == job_id
    assert body["building_graph"] is not None
    assert body["building_graph"]["metadata"]["input_source"] == "FLOOR_PLAN_IMAGE"


def test_jobs_endpoint_resolves_channel_b_cad_job(
    client: TestClient, sample_dxf_bytes: bytes
) -> None:
    files = {"file": ("plan.dxf", sample_dxf_bytes, "application/octet-stream")}
    post = client.post("/api/v1/building/upload/cad", files=files)
    job_id = post.json()["job_id"]

    r = client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["building_graph"]["metadata"]["input_source"] == "DXF_FILE"


def test_jobs_endpoint_unknown_id_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/jobs/no-such-job")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Review endpoint over async output
# ---------------------------------------------------------------------------


def test_review_endpoint_applies_override_to_async_job(client: TestClient) -> None:
    """The unified review endpoint must also work on Channel-C output."""

    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    post = client.post("/api/v1/building/upload/image", files=files)
    job_id = post.json()["job_id"]

    # First resolve the job to grab an overrideable assumption id.
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    register = status["building_graph"]["metadata"]["assumption_register"]
    overrideable = next(a for a in register if a["overrideable"])
    aid = overrideable["id"]

    payload = {
        "overrides": [
            {
                "assumption_id": aid,
                "value": overrideable["value"],
                "source": "reviewer-test",
            }
        ],
        "reviewer": "jdoe",
    }
    r = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == job_id
    updated = next(
        a for a in body["building_graph"]["metadata"]["assumption_register"]
        if a["id"] == aid
    )
    assert updated["was_overridden"] is True
    assert updated["override_source"].startswith("reviewer-test")


def test_review_404_on_unknown_job(client: TestClient) -> None:
    payload = {
        "overrides": [{"assumption_id": "anything", "value": 1, "source": "x"}]
    }
    r = client.post("/api/v1/jobs/no-such/review", json=payload)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Store wiring
# ---------------------------------------------------------------------------


def test_async_job_store_is_populated(client: TestClient) -> None:
    """The image endpoint writes into the shared store; jobs resolves from it."""

    from src.api import async_job_store

    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    post = client.post("/api/v1/building/upload/image", files=files)
    job_id = post.json()["job_id"]

    record = async_job_store.get(job_id)
    assert record is not None
    assert record.channel == "image"
    assert record.status == "completed"
    assert record.building_graph is not None
