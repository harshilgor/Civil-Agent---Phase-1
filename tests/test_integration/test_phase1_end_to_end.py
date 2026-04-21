"""Phase 1 end-to-end contract tests — one per input channel.

These are the pre-merge quality gate for Phase 1.  Unlike the per-module
tests they exercise the *real* pipeline through the FastAPI surface with
no injected fakes: Channel A builds from a structured form payload,
Channel B parses a live DXF through the real ezdxf/graph-builder stack,
and Channel C runs an actual floor-plan image through the CV pipeline
with real model weights loaded from disk.

Each test asserts the Phase 1 *contract* that every downstream stage
(Phase 2 structural, Phase 3 load & assumption engine, the review UI)
depends on:

1.  ``schema_version`` matches :data:`src.schema.SCHEMA_VERSION` — no
    silent skew.
2.  ``metadata.job_id`` threads from the initial upload response
    through to the stored graph.
3.  ``metadata.input_source`` matches the channel that produced the
    graph, so provenance filters work downstream.
4.  ``metadata.assumption_register`` carries at least one auditable
    :class:`AssumptionRecord`.  Silent defaults are a shipping bug.
5.  ``metadata.completeness.overall`` clears the review gate
    (:data:`HUMAN_REVIEW_THRESHOLD`).
6.  Every Building Graph element (wall, room, opening, column, core)
    carries a non-null :class:`ProvenanceRecord` whose ``detector_source``
    is a known producer and whose ``run_id`` equals the job id.

Channel C runs only when real model weights are on disk
(``RUN_REQUIRES_WEIGHTS=1`` + ``requires_weights`` marker).  CI stays
green without them; the pre-merge environment flips the env var on.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.schema import SCHEMA_VERSION
from src.schema.enums import DetectorSource
from src.utils.completeness_scorer import HUMAN_REVIEW_THRESHOLD


# ---------------------------------------------------------------------------
# Shared fixtures and the contract assertion helper
# ---------------------------------------------------------------------------


# The DetectorSource enum is the closed set of producers that may stamp
# a graph element.  Any element whose provenance.detector_source isn't
# in this set is a bug — usually a stale string literal that bypassed
# the enum.
_KNOWN_DETECTOR_SOURCES: frozenset[str] = frozenset(s.value for s in DetectorSource)


@pytest.fixture()
def client() -> TestClient:
    # A fresh app per test — the module-level stores in
    # src.api.structured_input / async_job_store are already reset by
    # the autouse fixture in tests/conftest.py, but a fresh client also
    # sidesteps any lingering routing state.
    return TestClient(create_app())


def _iter_elements(graph: dict[str, Any]):
    """Yield (kind, element_dict) for every element that must carry provenance."""

    for wall in graph.get("walls", []):
        yield "wall", wall
    for room in graph.get("rooms", []):
        yield "room", room
    for opening in graph.get("openings", []):
        yield "opening", opening
    for column in graph.get("column_candidates", []):
        yield "column", column
    for core in graph.get("cores", []):
        yield "core", core


def _assert_phase1_contract(
    graph: dict[str, Any],
    *,
    expected_input_source: str,
    expected_job_id: str,
) -> None:
    """Assert every invariant every Phase 1 channel must honour.

    Kept deliberately strict — a test that drops even one of these
    checks loses the contract value.  Channel-specific assertions
    (wall counts, detector source flavour, etc.) live in the
    per-channel tests below on top of this call.
    """

    # (1) schema version pin.
    assert graph["schema_version"] == SCHEMA_VERSION, (
        f"schema_version {graph['schema_version']!r} != {SCHEMA_VERSION!r}; "
        "the builder is emitting a stale schema."
    )

    meta = graph["metadata"]

    # (2) job id threading.  This is the single identifier the frontend
    # uses to correlate the upload response with the stored graph.
    assert meta["job_id"] == expected_job_id, (
        f"metadata.job_id {meta['job_id']!r} != upload response id "
        f"{expected_job_id!r}; provenance will not resolve downstream."
    )

    # (3) input source must match the channel the test drove.
    assert meta["input_source"] == expected_input_source

    # (4) assumption register must be non-empty and well-formed.
    register = meta["assumption_register"]
    assert isinstance(register, list) and register, (
        "assumption_register is empty; a channel that made any "
        "derivation (default floor-to-floor, placeholder room, VLM "
        "gap-fill, etc.) must record at least one AssumptionRecord."
    )
    required_keys = {
        "id",
        "name",
        "value",
        "source",
        "confidence",
        "rationale",
        "overrideable",
    }
    for i, record in enumerate(register):
        assert required_keys.issubset(record.keys()), (
            f"assumption_register[{i}] missing keys "
            f"{required_keys - record.keys()}: {record!r}"
        )
        assert 0.0 <= record["confidence"] <= 1.0

    # (5) completeness gate.
    completeness = meta.get("completeness")
    assert completeness is not None, "metadata.completeness not populated"
    assert completeness["overall"] >= HUMAN_REVIEW_THRESHOLD, (
        f"completeness.overall {completeness['overall']} below review "
        f"gate {HUMAN_REVIEW_THRESHOLD}; this graph should have been "
        "flagged for human review."
    )

    # (6) provenance on every element, run_id == job_id.
    for kind, element in _iter_elements(graph):
        prov = element.get("provenance")
        assert prov is not None, (
            f"{kind} {element.get('id', '?')!r} has no provenance record"
        )
        assert prov.get("detector_source") in _KNOWN_DETECTOR_SOURCES, (
            f"{kind} {element.get('id', '?')!r} has unknown detector_source "
            f"{prov.get('detector_source')!r}"
        )
        assert prov.get("run_id") == expected_job_id, (
            f"{kind} {element.get('id', '?')!r} provenance.run_id "
            f"{prov.get('run_id')!r} != job_id {expected_job_id!r}"
        )


# ---------------------------------------------------------------------------
# Channel A — structured form
# ---------------------------------------------------------------------------


def test_channel_a_structured_form_produces_complete_graph(
    client: TestClient,
) -> None:
    """POST /building/structured → BuildingGraphResponse.

    Channel A is the simplest path: the graph is synthesised from the
    form payload directly, every element is STRUCTURED_FORM-sourced,
    and completeness should land high because the user supplied every
    top-level field.
    """

    payload = {
        "project_name": "Phase 1 E2E Tower",
        "location": {
            "lat": 40.7128,
            "lng": -74.0060,
            "city": "New York",
            "state": "NY",
            "country": "US",
        },
        "length_mm": 40000,
        "width_mm": 30000,
        "num_stories": 5,
        "floor_to_floor_mm": 3900,
        "ground_floor_height_mm": 4500,
        "occupancy_type": "OFFICE",
        "material_preference": "REINFORCED_CONCRETE",
        "preferred_bay_x_mm": 8000,
        "preferred_bay_y_mm": 8000,
    }

    resp = client.post("/api/v1/building/structured", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    graph = body["building_graph"]
    job_id = graph["metadata"]["job_id"]
    assert job_id, "Channel A must emit a job_id on every graph"

    _assert_phase1_contract(
        graph,
        expected_input_source="STRUCTURED_FORM",
        expected_job_id=job_id,
    )

    # Channel-A-specific invariants.  These are the deliberate contract
    # guarantees the form path carries over the generic Phase 1 contract.
    assert len(graph["walls"]) >= 4, "rectangular footprint must produce ≥ 4 facade walls"
    assert all(
        w["provenance"]["detector_source"] == DetectorSource.STRUCTURED_FORM.value
        for w in graph["walls"]
    ), "Channel A walls must be STRUCTURED_FORM-sourced end to end"
    assert len(graph["stories"]) == payload["num_stories"]
    assert graph["project"]["num_stories"] == payload["num_stories"]
    # Channel A emits a rich register (input source marker + f2f + bay prefs +
    # building code + roof type + wall thickness + room heuristic).
    assert len(graph["metadata"]["assumption_register"]) >= 5
    assert (
        graph["metadata"]["completeness"]["overall"] >= 0.8
    ), "Channel A with all fields supplied should comfortably clear 0.8"

    # The unified jobs endpoint must resolve the same graph for polling.
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["status"] == "completed"
    assert status["building_graph"]["metadata"]["job_id"] == job_id


# ---------------------------------------------------------------------------
# Channel B — real DXF
# ---------------------------------------------------------------------------


def test_channel_b_dxf_upload_produces_correct_wall_geometry(
    client: TestClient, e2e_dxf_bytes: bytes
) -> None:
    """POST /building/upload/cad → async job → real DXF through parser + builder.

    The synthetic DXF fixture (``e2e_dxf_bytes``, see local conftest)
    is a 20 000 × 15 000 mm rectangle with one interior divider,
    three grid lines per axis, a labelled OFFICE room, and one door.
    Its ``$INSUNITS`` header is explicitly set to mm so the parser's
    millimetre output matches the source coordinates 1:1 — the E2E
    test asserts the literal envelope, not just element presence.
    Exercises the full ezdxf → DXFParser → CadGraphBuilder → scorer
    → async store path end to end.
    """

    files = {"file": ("plan.dxf", e2e_dxf_bytes, "application/octet-stream")}
    upload = client.post("/api/v1/building/upload/cad", files=files)
    assert upload.status_code == 202, upload.text
    upload_body = upload.json()
    job_id = upload_body["job_id"]
    assert upload_body["file_type"] == "DXF"

    # Eager mode finishes the task synchronously, so the first poll
    # should already see ``completed``.
    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["status"] == "completed", (
        f"Channel B job did not complete in eager mode; got status="
        f"{status['status']!r}, error={status.get('error')!r}"
    )
    graph = status["building_graph"]

    _assert_phase1_contract(
        graph,
        expected_input_source="DXF_FILE",
        expected_job_id=job_id,
    )

    # Channel-B-specific invariants — the geometry half of the test.
    walls = graph["walls"]
    assert walls, "DXF with five wall lines must produce non-empty walls"
    assert all(
        w["provenance"]["detector_source"] == DetectorSource.CAD_DIRECT.value
        for w in walls
    ), "every Channel B wall must carry CAD_DIRECT provenance"

    # Wall endpoints must live inside the 20 000 × 15 000 mm envelope
    # (with a 1 mm tolerance for floating-point drift from the parse).
    for wall in walls:
        for pt in (wall["start"], wall["end"]):
            x, y = pt
            assert -1.0 <= x <= 20000.0 + 1.0, (
                f"wall endpoint x={x} outside the 20 000 mm DXF envelope"
            )
            assert -1.0 <= y <= 15000.0 + 1.0, (
                f"wall endpoint y={y} outside the 15 000 mm DXF envelope"
            )

    # The wall graph must span the full 20 000 × 15 000 envelope.  The
    # CAD builder classifies every wall as STRUCTURAL (no
    # exterior/interior heuristic runs on DXF geometry alone), so we
    # assert on the bounding box rather than on a FACADE label.
    xs = [pt[0] for w in walls for pt in (w["start"], w["end"])]
    ys = [pt[1] for w in walls for pt in (w["start"], w["end"])]
    assert max(xs) - min(xs) >= 20000.0 - 1.0, (
        f"wall-graph X extent {max(xs) - min(xs):.1f} mm is smaller than "
        "the 20 000 mm DXF footprint — the parser is dropping walls"
    )
    assert max(ys) - min(ys) >= 15000.0 - 1.0, (
        f"wall-graph Y extent {max(ys) - min(ys):.1f} mm is smaller than "
        "the 15 000 mm DXF footprint — the parser is dropping walls"
    )

    # Grid must be present (the fixture draws three lines per axis).
    grid = graph["grid"]
    assert len(grid["x_lines"]) >= 2 and len(grid["y_lines"]) >= 2, (
        "S-GRID layer must produce grid lines on both axes"
    )


# ---------------------------------------------------------------------------
# Channel C — real image + real weights (gated by requires_weights)
# ---------------------------------------------------------------------------


_E2E_IMAGE_ENV = "CIVIL_AGENT_E2E_IMAGE_PATH"
_DEFAULT_E2E_IMAGE_CANDIDATES = (
    "sample_model_tester_img_2.png",
    "sample_model_tester_img.png",
    "sample_model_tester_img_ocr_viz.png",
)


def _resolve_channel_c_image() -> Path:
    """Find a real floor-plan image for the Channel C E2E test.

    Precedence:
    1. ``$CIVIL_AGENT_E2E_IMAGE_PATH`` — explicit override for the
       pre-merge environment.  Honoured even if the file is outside
       the workspace.
    2. A known sample image at the repo root.  These are the inputs the
       ``test_scripts/model_tester_runner.py`` script uses, so they're
       the ones most likely to be present in a weights-enabled checkout.

    Calls :func:`pytest.skip` when nothing resolves; the test still
    belongs in the suite (the weights gate is the primary skip
    trigger) but we don't want to fail for a missing input asset.
    """

    override = os.environ.get(_E2E_IMAGE_ENV)
    if override:
        p = Path(override)
        if p.is_file():
            return p
        pytest.skip(
            f"{_E2E_IMAGE_ENV}={override!r} does not point at an existing file"
        )

    repo_root = Path(__file__).resolve().parents[2]
    for name in _DEFAULT_E2E_IMAGE_CANDIDATES:
        candidate = repo_root / name
        if candidate.is_file():
            return candidate

    pytest.skip(
        "no floor-plan image available for the Channel C E2E test; "
        f"set {_E2E_IMAGE_ENV} or drop one of "
        f"{list(_DEFAULT_E2E_IMAGE_CANDIDATES)} at the repo root"
    )


@pytest.mark.requires_weights
def test_channel_c_image_upload_with_real_weights_produces_ml_graph(
    client: TestClient,
) -> None:
    """POST /building/upload/image → Channel C pipeline with real weights.

    Marked ``requires_weights`` so CI skips it.  When
    ``RUN_REQUIRES_WEIGHTS=1`` is exported (pre-merge environment with
    the model files on disk) this test drives the full Stage 1-10
    pipeline — preprocess, VLM classify, ML segment + detect,
    vectorise, geometry post-process, BuildingGraph assembly — and
    asserts the real-weights path produces a non-degraded graph with
    ML-sourced elements.

    Failure modes this test catches that the fake-ML integration
    tests miss:

    * manifest/weights-file drift (the loader resolves but the file
      on disk is from a different model version);
    * a real Claude API response that the VLM parser chokes on;
    * a vectoriser → geometry post-processor seam that holds on
      synthetic masks but breaks on a real mask's topology.
    """

    image_path = _resolve_channel_c_image()
    image_bytes = image_path.read_bytes()
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    files = {"file": (image_path.name, io.BytesIO(image_bytes), mime)}
    upload = client.post("/api/v1/building/upload/image", files=files)
    assert upload.status_code == 202, upload.text
    job_id = upload.json()["job_id"]

    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["status"] == "completed", (
        f"Channel C job did not complete; status={status['status']!r}, "
        f"error={status.get('error')!r}"
    )
    graph = status["building_graph"]

    _assert_phase1_contract(
        graph,
        expected_input_source="FLOOR_PLAN_IMAGE",
        expected_job_id=job_id,
    )

    # Channel-C-specific invariants.  With real weights the pipeline
    # must produce ML-sourced walls and must *not* collapse into the
    # degraded-placeholder path.
    warnings = graph["metadata"]["warnings"]
    assert "degraded_placeholder_graph_emitted" not in warnings, (
        "real-weights Channel C run fell back to the degraded placeholder; "
        f"warnings={warnings!r}"
    )
    assert "image_pipeline_produced_no_walls" not in warnings, (
        "real-weights Channel C run produced zero walls; "
        f"warnings={warnings!r}"
    )

    walls = graph["walls"]
    assert walls, "real-weights Channel C run must emit non-empty walls"

    ml_detectors = {
        DetectorSource.CUBICASA_HG.value,
        DetectorSource.SMP_UNET.value,
        DetectorSource.YOLO_SEG.value,
    }
    wall_detectors = {w["provenance"]["detector_source"] for w in walls}
    assert wall_detectors & ml_detectors, (
        f"Channel C walls must carry an ML detector source; got "
        f"{sorted(wall_detectors)}"
    )

    # Every element must still carry a real model_id / run_id pair so
    # the provenance is reproducible.
    for _, element in _iter_elements(graph):
        prov = element["provenance"]
        # model_id is optional on non-ML elements (user-supplied rooms,
        # VLM-classified metadata) but must be present when the
        # detector is ML.
        if prov["detector_source"] in ml_detectors:
            assert prov.get("model_id"), (
                f"ML-sourced element missing provenance.model_id: "
                f"{element.get('id')!r}"
            )
