"""Unit tests for :mod:`src.cv.building_type_classifier`.

Tests inject a mocked Anthropic client rather than hitting the real API
so they run deterministically in CI without credentials.  The mock
pattern mirrors ``tests/test_api/test_async_job_store.py`` (MagicMock
wrapping the third-party entry point).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.cv.building_type_classifier import (
    DEFAULT_CLAUDE_MODEL,
    UNAVAILABLE_RESULT,
    BuildingTypeClassifier,
    ClassificationResult,
    _best_json_object,
    _parse_classification_json,
)
from src.schema.enums import BuildingType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _claude_response(text: str) -> SimpleNamespace:
    """Mimic the shape ``anthropic.Anthropic().messages.create(...)`` returns.

    The real SDK yields a ``Message`` whose ``content`` is a list of
    content blocks; each block has a ``.text`` attribute when it is a
    text block.  ``SimpleNamespace`` is enough to stand in for the
    duck-typing the classifier performs.
    """

    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _make_classifier_with_response(text: str) -> BuildingTypeClassifier:
    client = MagicMock()
    client.messages.create.return_value = _claude_response(text)
    return BuildingTypeClassifier(client=client)


# ---------------------------------------------------------------------------
# No-key / unavailable path
# ---------------------------------------------------------------------------


class TestUnavailable:
    def test_no_api_key_returns_unavailable(self) -> None:
        clf = BuildingTypeClassifier()
        assert clf.is_available is False
        result = clf.classify(b"fake-png-bytes")
        assert result is UNAVAILABLE_RESULT
        assert result.building_type is BuildingType.UNKNOWN
        assert result.confidence == 0.0
        assert result.is_fallback is True

    def test_unavailable_result_model_id_matches_default(self) -> None:
        """The unavailable fallback still carries the canonical model id
        so provenance records stay consistent."""
        assert UNAVAILABLE_RESULT.model_id == DEFAULT_CLAUDE_MODEL


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_commercial_classification(self) -> None:
        clf = _make_classifier_with_response(
            '{"building_type": "COMMERCIAL", "confidence": 0.87, '
            '"rationale": "Open-plan desks and large lobby are characteristic of an office."}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.COMMERCIAL
        assert result.confidence == pytest.approx(0.87)
        assert "open-plan" in result.rationale.lower()
        assert result.is_fallback is False

    def test_residential_classification(self) -> None:
        clf = _make_classifier_with_response(
            '{"building_type": "RESIDENTIAL", "confidence": 0.92, '
            '"rationale": "Bedrooms, kitchen and bathrooms visible."}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.RESIDENTIAL
        assert result.confidence == pytest.approx(0.92)

    def test_model_id_stamped_on_result(self) -> None:
        clf = _make_classifier_with_response(
            '{"building_type": "INSTITUTIONAL", "confidence": 0.75, "rationale": "Classrooms."}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.model_id == DEFAULT_CLAUDE_MODEL

    def test_custom_model_override(self) -> None:
        client = MagicMock()
        client.messages.create.return_value = _claude_response(
            '{"building_type": "COMMERCIAL", "confidence": 0.6, "rationale": "x"}'
        )
        clf = BuildingTypeClassifier(client=client, model="claude-test-99")
        result = clf.classify(b"fake-png-bytes")
        assert result.model_id == "claude-test-99"
        # The override must be what the SDK was actually called with.
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-test-99"

    def test_image_is_base64_encoded(self) -> None:
        """The caller passes raw PNG bytes; the classifier must
        base64-encode them before sending them to the SDK."""
        import base64

        client = MagicMock()
        client.messages.create.return_value = _claude_response(
            '{"building_type": "RESIDENTIAL", "confidence": 0.9, "rationale": "x"}'
        )
        clf = BuildingTypeClassifier(client=client)
        png_bytes = b"PNG\x00SAMPLE"
        clf.classify(png_bytes)

        message_blocks = client.messages.create.call_args.kwargs["messages"][0]["content"]
        image_block = next(b for b in message_blocks if b.get("type") == "image")
        assert image_block["source"]["media_type"] == "image/png"
        assert image_block["source"]["data"] == base64.b64encode(png_bytes).decode()


# ---------------------------------------------------------------------------
# Robustness — malformed responses, API errors, scale handling
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_malformed_json_falls_back_to_unknown(self) -> None:
        clf = _make_classifier_with_response("This is not JSON at all.")
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.UNKNOWN
        assert result.is_fallback is True
        assert result.raw_response == "This is not JSON at all."

    def test_json_with_unknown_building_type_rejected(self) -> None:
        """A response that cites a label outside the BuildingType enum
        must degrade gracefully — we never fabricate an enum member."""
        clf = _make_classifier_with_response(
            '{"building_type": "STADIUM", "confidence": 0.9, "rationale": "x"}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.UNKNOWN
        assert result.is_fallback is True

    def test_json_embedded_in_prose_is_extracted(self) -> None:
        clf = _make_classifier_with_response(
            'Sure, looking at this image:\n\n'
            '{"building_type": "INDUSTRIAL", "confidence": 0.71, '
            '"rationale": "Loading docks and large clear-span."}'
            '\n\nHope this helps!'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.INDUSTRIAL
        assert result.confidence == pytest.approx(0.71)

    def test_confidence_out_of_range_is_clamped(self) -> None:
        """Claude occasionally emits 0-100 scale; clamp into [0,1]."""
        clf = _make_classifier_with_response(
            '{"building_type": "RESIDENTIAL", "confidence": 87, "rationale": "x"}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert 0.0 <= result.confidence <= 1.0
        assert result.confidence == pytest.approx(0.87)

    def test_api_error_falls_back_gracefully(self) -> None:
        """Any exception from the SDK (network, auth, rate limit) is
        swallowed into a fallback result — the worker never crashes on
        a transient VLM failure."""
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("429 too many requests")
        clf = BuildingTypeClassifier(client=client)
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.UNKNOWN
        assert result.is_fallback is True
        assert "429" in result.rationale

    def test_empty_content_list_handled(self) -> None:
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(content=[])
        clf = BuildingTypeClassifier(client=client)
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.UNKNOWN
        assert result.is_fallback is True

    def test_case_insensitive_building_type(self) -> None:
        """The enum is upper-case, but the parser should tolerate the
        occasional lower-cased response."""
        clf = _make_classifier_with_response(
            '{"building_type": "residential", "confidence": 0.8, "rationale": "x"}'
        )
        result = clf.classify(b"fake-png-bytes")
        assert result.building_type is BuildingType.RESIDENTIAL


# ---------------------------------------------------------------------------
# Module-level parsing helpers (unit-testable without a classifier)
# ---------------------------------------------------------------------------


class TestParsingHelpers:
    def test_best_json_object_simple(self) -> None:
        assert _best_json_object('{"a":1}') == '{"a":1}'

    def test_best_json_object_with_preamble(self) -> None:
        assert _best_json_object('foo bar {"a":1} tail') == '{"a":1}'

    def test_best_json_object_with_nested_braces(self) -> None:
        raw = '{"outer": {"inner": 1}}'
        assert _best_json_object(raw) == raw

    def test_best_json_object_none_when_absent(self) -> None:
        assert _best_json_object("no braces here") is None

    def test_parse_classification_json_happy(self) -> None:
        parsed = _parse_classification_json(
            '{"building_type": "COMMERCIAL", "confidence": 0.8, "rationale": "x"}'
        )
        assert parsed is not None
        assert parsed["building_type"] is BuildingType.COMMERCIAL

    def test_parse_classification_json_missing_fields(self) -> None:
        assert _parse_classification_json('{"building_type": "COMMERCIAL"}') == {
            "building_type": BuildingType.COMMERCIAL,
            "confidence": 0.0,
            "rationale": "(no rationale provided)",
        }

    def test_parse_classification_json_invalid_confidence(self) -> None:
        assert (
            _parse_classification_json(
                '{"building_type": "COMMERCIAL", "confidence": "not-a-number"}'
            )
            is None
        )


# ---------------------------------------------------------------------------
# ClassificationResult dataclass sanity
# ---------------------------------------------------------------------------


class TestClassificationResult:
    def test_immutable(self) -> None:
        r = ClassificationResult(
            building_type=BuildingType.COMMERCIAL,
            confidence=0.5,
            rationale="x",
            model_id="m",
        )
        with pytest.raises(Exception):  # frozen dataclass → FrozenInstanceError
            r.confidence = 0.9  # type: ignore[misc]
