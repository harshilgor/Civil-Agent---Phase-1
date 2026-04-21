"""Step-11 review endpoints: ``GET`` and extended ``POST`` /api/v1/jobs/{id}/review.

Happy paths and failure modes against the full FastAPI stack.  The
service-level correction logic is tested directly in
``tests/test_core/test_review_service.py``; this module focuses on
the HTTP contract — status codes, response shape, routing across
channels.
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


def _structured_payload() -> dict:
    return {
        "project_name": "Step 11 Tower",
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


def _channel_a_job(client: TestClient) -> tuple[str, dict]:
    resp = client.post("/api/v1/building/structured", json=_structured_payload())
    assert resp.status_code == 201
    body = resp.json()
    return body["building_graph"]["metadata"]["job_id"], body


def _channel_c_job(client: TestClient) -> str:
    files = {"file": ("plan.png", _tiny_png_bytes(), "image/png")}
    resp = client.post("/api/v1/building/upload/image", files=files)
    # Image endpoint returns 202 Accepted (async handoff); in eager mode
    # the task has nevertheless already completed by the time we poll.
    assert resp.status_code in (200, 202), resp.text
    return resp.json()["job_id"]


# ---------------------------------------------------------------------------
# GET /review
# ---------------------------------------------------------------------------


class TestReviewSnapshotEndpoint:
    def test_channel_a_snapshot_has_no_review_required(
        self, client: TestClient
    ) -> None:
        job_id, _ = _channel_a_job(client)
        resp = client.get(f"/api/v1/jobs/{job_id}/review")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["job_id"] == job_id
        # Channel A graphs are clean enough that completeness is >= 0.5
        # and no elements fall below the threshold.
        assert body["review_required"] is False
        assert body["low_confidence_elements"] == []
        # Overrideable assumptions must be surfaced (Channel A emits many).
        assert len(body["overrideable_assumptions"]) > 0
        # And they're sorted weakest-first.
        confs = [a["confidence"] for a in body["overrideable_assumptions"]]
        assert confs == sorted(confs)
        # Each entry carries the reviewer-facing projection fields.
        for a in body["overrideable_assumptions"]:
            assert {"id", "name", "value", "confidence_level", "rationale"}.issubset(
                a.keys()
            )

    def test_channel_c_degraded_job_flags_review_required(
        self, client: TestClient
    ) -> None:
        """A CI Channel-C run has no real ML weights, so the pipeline
        emits a degraded placeholder graph — which the completeness
        scorer correctly flags as needing review."""

        job_id = _channel_c_job(client)
        resp = client.get(f"/api/v1/jobs/{job_id}/review")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["review_required"] is True
        # Degraded placeholder rooms carry confidence=0.40 which is below
        # the low-confidence threshold — they must surface.
        kinds = {e["kind"] for e in body["low_confidence_elements"]}
        assert "room" in kinds

    def test_snapshot_404_on_unknown_job(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs/no-such-job/review")
        assert resp.status_code == 404

    def test_snapshot_carries_completeness_axes(self, client: TestClient) -> None:
        job_id, _ = _channel_a_job(client)
        body = client.get(f"/api/v1/jobs/{job_id}/review").json()
        assert body["completeness"] is not None
        assert {"overall", "geometry", "semantics", "detector_coverage"}.issubset(
            body["completeness"].keys()
        )
        assert 0.0 <= body["completeness"]["overall"] <= 1.0


# ---------------------------------------------------------------------------
# POST /review — corrections
# ---------------------------------------------------------------------------


class TestReviewCorrectionEndpoint:
    def test_wall_correction_stamps_user_override_provenance(
        self, client: TestClient
    ) -> None:
        job_id, create_body = _channel_a_job(client)
        wall_id = create_body["building_graph"]["walls"][0]["id"]
        original_detector = create_body["building_graph"]["walls"][0]["provenance"][
            "detector_source"
        ]

        payload = {
            "corrections": [
                {
                    "target": "wall",
                    "id": wall_id,
                    "fields": {"type": "STRUCTURAL", "thickness_mm": 300.0},
                }
            ],
            "reviewer": "jdoe",
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        updated_wall = next(
            w for w in body["building_graph"]["walls"] if w["id"] == wall_id
        )
        assert updated_wall["type"] == "STRUCTURAL"
        assert updated_wall["thickness_mm"] == 300.0
        assert updated_wall["confidence"] == 1.0
        assert updated_wall["provenance"]["detector_source"] == "USER_OVERRIDE"
        assert updated_wall["provenance"]["confidence_from_model"] == 1.0
        # Prior detector survives in the notes for auditability.
        notes = updated_wall["provenance"]["notes"] or ""
        assert original_detector in notes
        assert "jdoe" in notes

    def test_mixed_payload_applies_override_then_correction(
        self, client: TestClient
    ) -> None:
        job_id, create_body = _channel_a_job(client)
        register = create_body["building_graph"]["metadata"]["assumption_register"]
        overrideable = next(a for a in register if a["overrideable"])
        wall_id = create_body["building_graph"]["walls"][0]["id"]

        payload = {
            "overrides": [
                {
                    "assumption_id": overrideable["id"],
                    "value": overrideable["value"],
                    "source": "reviewer-mixed",
                }
            ],
            "corrections": [
                {
                    "target": "wall",
                    "id": wall_id,
                    "fields": {"thickness_mm": 275.0},
                }
            ],
            "reviewer": "eng-01",
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        updated_assumption = next(
            a for a in body["building_graph"]["metadata"]["assumption_register"]
            if a["id"] == overrideable["id"]
        )
        assert updated_assumption["was_overridden"] is True
        assert updated_assumption["override_source"].startswith("reviewer-mixed")

        updated_wall = next(
            w for w in body["building_graph"]["walls"] if w["id"] == wall_id
        )
        assert updated_wall["thickness_mm"] == 275.0
        assert updated_wall["provenance"]["detector_source"] == "USER_OVERRIDE"

    def test_correction_unknown_element_is_404(self, client: TestClient) -> None:
        job_id, _ = _channel_a_job(client)
        payload = {
            "corrections": [
                {
                    "target": "wall",
                    "id": "wall-does-not-exist",
                    "fields": {"thickness_mm": 400},
                }
            ]
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 404
        assert "wall-does-not-exist" in resp.json()["detail"]

    def test_correction_unknown_field_is_422(self, client: TestClient) -> None:
        job_id, create_body = _channel_a_job(client)
        wall_id = create_body["building_graph"]["walls"][0]["id"]
        payload = {
            "corrections": [
                {
                    "target": "wall",
                    "id": wall_id,
                    "fields": {"confidence": 0.1},
                }
            ]
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 422
        assert "non-editable" in resp.json()["detail"].lower()

    def test_correction_invalid_value_is_422(self, client: TestClient) -> None:
        """Pydantic re-validation of the merged model must fail cleanly."""

        job_id, create_body = _channel_a_job(client)
        wall_id = create_body["building_graph"]["walls"][0]["id"]
        payload = {
            "corrections": [
                {
                    "target": "wall",
                    "id": wall_id,
                    "fields": {"thickness_mm": -5},  # violates gt=0
                }
            ]
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 422

    def test_empty_payload_is_422(self, client: TestClient) -> None:
        job_id, _ = _channel_a_job(client)
        resp = client.post(
            f"/api/v1/jobs/{job_id}/review",
            json={"overrides": [], "corrections": []},
        )
        assert resp.status_code == 422

    def test_column_correction_uses_integer_index(
        self, client: TestClient
    ) -> None:
        job_id, create_body = _channel_a_job(client)
        assert len(create_body["building_graph"]["column_candidates"]) > 0

        payload = {
            "corrections": [
                {
                    "target": "column",
                    "id": "0",
                    "fields": {"is_required": True, "notes": "approved"},
                }
            ],
            "reviewer": "eng-02",
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 200, resp.text
        col = resp.json()["building_graph"]["column_candidates"][0]
        assert col["is_required"] is True
        assert col["notes"] == "approved"
        assert col["confidence"] == 1.0
        assert col["provenance"]["detector_source"] == "USER_OVERRIDE"

    def test_channel_c_correction_roundtrips_through_async_store(
        self, client: TestClient
    ) -> None:
        """Corrections on a Channel-C job must surface through the
        unified jobs GET too — same Building Graph, same store."""

        job_id = _channel_c_job(client)
        # Degraded placeholder has one room; grab its id and rename it.
        status = client.get(f"/api/v1/jobs/{job_id}").json()
        room = status["building_graph"]["rooms"][0]
        room_id = room["id"]

        payload = {
            "corrections": [
                {
                    "target": "room",
                    "id": room_id,
                    "fields": {"label": "Reviewer Lobby"},
                }
            ],
            "reviewer": "qa-01",
        }
        resp = client.post(f"/api/v1/jobs/{job_id}/review", json=payload)
        assert resp.status_code == 200, resp.text

        # Re-fetch via the unified jobs endpoint to prove the mutation
        # hit the shared async store, not a response-local copy.
        refetched = client.get(f"/api/v1/jobs/{job_id}").json()
        refetched_room = next(
            r for r in refetched["building_graph"]["rooms"] if r["id"] == room_id
        )
        assert refetched_room["label"] == "Reviewer Lobby"
        assert refetched_room["confidence"] == 1.0
        assert refetched_room["provenance"]["detector_source"] == "USER_OVERRIDE"


# ---------------------------------------------------------------------------
# GET + POST interaction — the review flow
# ---------------------------------------------------------------------------


def test_low_confidence_element_disappears_after_correction(
    client: TestClient,
) -> None:
    """Correcting a low-confidence element must clear it from the next
    snapshot — confidence is clamped to 1.0 on approval."""

    job_id = _channel_c_job(client)
    snap = client.get(f"/api/v1/jobs/{job_id}/review").json()
    rooms = [e for e in snap["low_confidence_elements"] if e["kind"] == "room"]
    assert rooms, "expected the degraded placeholder room to surface"
    target_id = rooms[0]["id"]

    client.post(
        f"/api/v1/jobs/{job_id}/review",
        json={
            "corrections": [
                {
                    "target": "room",
                    "id": target_id,
                    "fields": {"label": "Approved"},
                }
            ]
        },
    ).raise_for_status()

    snap2 = client.get(f"/api/v1/jobs/{job_id}/review").json()
    still_flagged = [
        e
        for e in snap2["low_confidence_elements"]
        if e["kind"] == "room" and e["id"] == target_id
    ]
    assert still_flagged == []
