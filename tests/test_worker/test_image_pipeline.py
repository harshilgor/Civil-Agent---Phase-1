"""End-to-end integration tests for Channel C's Stage-1 through Stage-10 pipeline.

These tests drive :func:`src.worker.tasks._run_image_pipeline` (and the
Celery task + in-process twin that wrap it) against real PNG fixtures,
with the Anthropic client monkey-patched so the VLM call never leaves
the test process.

The production weights manifest points to checkpoint files that don't
exist in CI (``cubicasa_hg_v1.pkl`` etc.), so the ML engine fails to
resolve and the :class:`ImageGraphBuilder` falls through to the
*degraded* path.  That's the correct behaviour — the graph is
schema-valid with a loud ``channel_c_degraded_placeholder`` assumption
record so a reviewer can see exactly why the pipeline collapsed.

Happy-path tests (wall mask → real walls → real building graph) are in
``tests/test_core/test_image_graph_builder.py``; they inject a fake
:class:`MLEngine` that produces a synthetic wall mask and exercise the
full Stage 3-10 flow without needing torch or any real weights.
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png(path: Path, *, size: tuple[int, int] = (400, 300)) -> Path:
    """Write a small synthetic floor-plan-ish PNG to *path* and return it."""

    img = Image.new("RGB", size, color=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


def _claude_response(building_type: str, confidence: float, rationale: str = "x") -> SimpleNamespace:
    """Shape the real Anthropic SDK returns, simplified to what we parse."""

    body = (
        f'{{"building_type": "{building_type}", '
        f'"confidence": {confidence}, '
        f'"rationale": "{rationale}"}}'
    )
    return SimpleNamespace(content=[SimpleNamespace(text=body)])


@pytest.fixture()
def mock_anthropic(monkeypatch: pytest.MonkeyPatch):
    """Monkey-patch ``anthropic.Anthropic`` so the classifier picks up a
    MagicMock client rather than making real network calls.  Returns the
    mock client so the test can configure its ``messages.create`` return
    value per-case.
    """

    import anthropic

    client = MagicMock()
    client.messages.create.return_value = _claude_response("COMMERCIAL", 0.83)

    def _factory(*_args, **_kwargs):
        return client

    monkeypatch.setattr(anthropic, "Anthropic", _factory)

    # Classifier only instantiates a client when an api_key is set on the
    # Settings object.  Wire in a placeholder so the ``if api_key:`` gate
    # passes even in CI runs without a real key.
    from src.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "test-key-stub", raising=False)
    return client


# ---------------------------------------------------------------------------
# _run_image_pipeline — happy path
# ---------------------------------------------------------------------------


class TestImagePipelineHappyPath:
    def test_vlm_classification_drives_inferred_building_type(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """The VLM's classification must land on
        ``metadata.inferred_building_type`` (not the occupancy-derived
        default) and the assumption register must record the decision.
        """

        from src.worker.tasks import _run_image_pipeline

        mock_anthropic.messages.create.return_value = _claude_response(
            "RESIDENTIAL", 0.91, "Bedrooms and a kitchen."
        )
        png = _make_png(tmp_path / "plan.png")

        result = _run_image_pipeline("job-c-1", str(png))

        assert result["status"] == "ok"
        assert result["channel"] == "image"
        # Step 10 landed the full pipeline — under CI the weights are
        # unresolvable so we hit the degraded placeholder path, not the
        # happy path.  The string must still announce Stage 10 completion
        # (not a "we stopped at Stage 2" marker) so the reviewer sees the
        # run was attempted end-to-end.
        assert result["stage_completed"].startswith("stage_10_")
        assert result["stub"] is True  # degraded: no walls resolvable in CI

        cls = result["classification"]
        assert cls["building_type"] == "RESIDENTIAL"
        assert cls["confidence"] == pytest.approx(0.91)
        assert cls["is_fallback"] is False
        assert cls["model_id"].startswith("claude")

        graph = result["building_graph"]
        assert graph["metadata"]["inferred_building_type"] == "RESIDENTIAL"

        register = graph["metadata"]["assumption_register"]
        vlm_record = next(
            r for r in register if r["id"] == "channel_c_vlm_building_type"
        )
        assert vlm_record["value"] == "RESIDENTIAL"
        assert vlm_record["overrideable"] is True
        assert "phase3.design" in vlm_record["affects_modules"]

        # The image preprocessing assumption is recorded non-overrideable.
        preproc = next(
            r for r in register if r["id"] == "channel_c_vlm_image_preprocess"
        )
        assert preproc["overrideable"] is False
        assert preproc["value"]["dpi_source"] in {"exif", "fallback", "pdf"}

        # The degraded-placeholder assumption must fire and be
        # overrideable — the reviewer can re-run with a different scale
        # / manifest if they know why the first pass collapsed.
        degraded = next(
            r for r in register if r["id"] == "channel_c_degraded_placeholder"
        )
        assert degraded["overrideable"] is True
        assert degraded["value"]["reason"] == "zero_walls_after_geometry_post_processor"

    def test_slot_selection_is_advisory_in_ci(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """In CI the residential weights don't exist on disk, so
        :meth:`MLEngine.from_loader` fails to resolve them and
        ``selected_slot`` reports ``None`` — the honest answer ("no
        weights loaded") rather than the aspirational one.

        The VLM classification itself must still land correctly on the
        graph so the reviewer sees the building type even when the
        downstream detector is missing.
        """

        from src.worker.tasks import _run_image_pipeline

        mock_anthropic.messages.create.return_value = _claude_response(
            "RESIDENTIAL", 0.9
        )
        png = _make_png(tmp_path / "plan.png")
        result = _run_image_pipeline("job-c-2", str(png))
        # Weights unresolvable in CI -> no slot actually loaded.
        assert result["selected_slot"] is None
        assert result["building_graph"]["metadata"]["inferred_building_type"] == "RESIDENTIAL"

    def test_commercial_classification_no_enabled_slot(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """COMMERCIAL has no enabled slot in the production manifest
        yet (wall_segmenter_commercial ships disabled until the SMP
        U-Net checkpoint lands).  The pipeline must still return
        successfully — ``selected_slot=None``, the VLM classification
        on the graph — so the reviewer sees the attempt even when the
        downstream detector is missing.
        """

        from src.worker.tasks import _run_image_pipeline

        mock_anthropic.messages.create.return_value = _claude_response(
            "COMMERCIAL", 0.82
        )
        png = _make_png(tmp_path / "plan.png")
        result = _run_image_pipeline("job-c-3", str(png))

        assert result["status"] == "ok"
        assert result["selected_slot"] is None
        assert result["classification"]["building_type"] == "COMMERCIAL"

    def test_anthropic_client_called_once_with_png(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """Exactly one Claude call per upload, and it must receive a
        base64-encoded PNG payload the size of the preprocessed image."""

        from src.worker.tasks import _run_image_pipeline

        png = _make_png(tmp_path / "plan.png")
        _run_image_pipeline("job-c-4", str(png))

        assert mock_anthropic.messages.create.call_count == 1
        kwargs = mock_anthropic.messages.create.call_args.kwargs
        image_block = next(
            b for b in kwargs["messages"][0]["content"] if b.get("type") == "image"
        )
        assert image_block["source"]["media_type"] == "image/png"
        assert len(image_block["source"]["data"]) > 100  # base64 payload present


# ---------------------------------------------------------------------------
# Fallback path — no API key
# ---------------------------------------------------------------------------


class TestImagePipelineFallback:
    def test_no_api_key_falls_back_to_occupancy_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """With no ``ANTHROPIC_API_KEY`` configured the classifier must
        short-circuit to ``UNAVAILABLE_RESULT`` and the graph must keep
        the occupancy-derived ``inferred_building_type`` rather than
        clobbering it with UNKNOWN."""

        from src.config import settings
        from src.worker.tasks import _run_image_pipeline

        monkeypatch.setattr(settings, "anthropic_api_key", None, raising=False)
        png = _make_png(tmp_path / "plan.png")

        result = _run_image_pipeline("job-c-fallback", str(png))

        cls = result["classification"]
        assert cls["is_fallback"] is True
        assert cls["building_type"] == "UNKNOWN"
        assert cls["confidence"] == 0.0

        # Synthetic graph is built from an OFFICE occupancy, which maps
        # to COMMERCIAL in the occupancy→BuildingType fallback table.
        graph = result["building_graph"]
        assert graph["metadata"]["inferred_building_type"] == "COMMERCIAL"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        from src.worker.tasks import _run_image_pipeline

        with pytest.raises(FileNotFoundError):
            _run_image_pipeline("job-c-missing", str(tmp_path / "missing.png"))


# ---------------------------------------------------------------------------
# Celery task + in-process twin
# ---------------------------------------------------------------------------


class TestProcessFloorPlanTask:
    def test_celery_task_delay_roundtrips_with_mocked_vlm(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """Under eager mode the Celery task must execute the real
        pipeline, and the result must carry VLM-driven metadata."""

        from src.worker.tasks import process_floor_plan

        assert process_floor_plan is not None
        mock_anthropic.messages.create.return_value = _claude_response(
            "INSTITUTIONAL", 0.74, "Classrooms and auditorium."
        )
        png = _make_png(tmp_path / "plan.png")

        async_result = process_floor_plan.delay("job-celery-1", str(png))
        payload = async_result.get(timeout=5)

        assert payload["status"] == "ok"
        assert payload["classification"]["building_type"] == "INSTITUTIONAL"

    def test_run_image_inprocess_equivalent_to_pipeline(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """The sync twin used by the fallback path must produce the same
        payload shape as the Celery task."""

        from src.worker.tasks import run_image_inprocess

        png = _make_png(tmp_path / "plan.png")
        payload = run_image_inprocess("job-inproc-1", str(png))
        assert payload["channel"] == "image"
        assert payload["stage_completed"].startswith("stage_10_")
        assert "classification" in payload

    def test_task_failure_propagates(
        self, tmp_path: Path, mock_anthropic: MagicMock
    ):
        """A non-existent image path must surface as a Celery task
        failure rather than a silent stub."""

        from src.worker.tasks import process_floor_plan

        assert process_floor_plan is not None
        with pytest.raises(Exception):
            process_floor_plan.delay(
                "job-celery-missing", str(tmp_path / "missing.png")
            ).get(timeout=5)
