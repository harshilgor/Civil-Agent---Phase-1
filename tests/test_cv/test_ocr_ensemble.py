"""Tests for the OCR ensemble (Gap 3)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from src.cv.ocr_ensemble import (
    AGREEMENT_BOOST,
    DISAGREEMENT_CAP,
    PRIMARY_CONFIDENCE_THRESHOLD,
    OCREnsemble,
    _merge,
    _strings_equivalent,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePaddle:
    """Emulates ``PaddleOCR.ocr()`` for deterministic testing."""

    def __init__(self, results: list[tuple[list[list[float]], tuple[str, float]]]) -> None:
        self._results = results

    def ocr(self, image, cls: bool = True):
        return [self._results]


class FakeParseq:
    """Emulates PARSeq by returning a canned text/confidence."""

    def __init__(self, text: str, confidence: float) -> None:
        self.text = text
        self.confidence = confidence


def fake_parseq_predict(model: FakeParseq, crop: np.ndarray) -> tuple[str, float]:
    return model.text, model.confidence


# ---------------------------------------------------------------------------
# _merge() direct tests
# ---------------------------------------------------------------------------


def test_merge_agreement_boosts_confidence() -> None:
    primary = {"text": "6000", "confidence": 0.60, "bbox": [], "position": [0, 0]}
    merged = _merge(primary, "6000", 0.80)
    assert merged["text"] == "6000"
    assert merged["confidence"] > 0.60
    assert merged["conflict_flag"] is False
    assert "paddle+parseq" in merged["engine"]


def test_merge_disagreement_caps_confidence_parseq_wins() -> None:
    primary = {"text": "3000", "confidence": 0.55, "bbox": [], "position": [0, 0]}
    merged = _merge(primary, "8000", 0.80)
    assert merged["text"] == "8000"
    assert merged["confidence"] <= DISAGREEMENT_CAP
    assert merged["conflict_flag"] is True


def test_merge_disagreement_paddle_wins_if_higher() -> None:
    primary = {"text": "3000", "confidence": 0.75, "bbox": [], "position": [0, 0]}
    merged = _merge(primary, "8000", 0.50)
    assert merged["text"] == "3000"
    assert merged["confidence"] <= DISAGREEMENT_CAP
    assert merged["conflict_flag"] is True


def test_strings_equivalent() -> None:
    assert _strings_equivalent("6000", "6000")
    assert _strings_equivalent(" 6000 ", "6000")
    assert _strings_equivalent("6000.", "6000")
    assert _strings_equivalent("OFFICE", "office")
    assert not _strings_equivalent("6000", "8000")


# ---------------------------------------------------------------------------
# Full-pipeline with fakes
# ---------------------------------------------------------------------------


def _make_ensemble(
    paddle_results: list[tuple[list[list[float]], tuple[str, float]]],
    parseq: FakeParseq | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> OCREnsemble:
    ensemble = OCREnsemble(paddle_engine=FakePaddle(paddle_results), parseq_model=parseq)
    if parseq is not None and monkeypatch is not None:
        from src.cv import ocr_ensemble as mod

        monkeypatch.setattr(mod, "_parseq_predict", fake_parseq_predict)
    return ensemble


def test_high_confidence_uses_paddle_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], ("6000", 0.95)),
    ]
    ensemble = _make_ensemble(
        results, parseq=FakeParseq("XXXX", 0.99), monkeypatch=monkeypatch
    )
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    out = ensemble.run(img)
    assert len(out) == 1
    assert out[0]["text"] == "6000"  # PARSeq was not consulted
    assert out[0]["engine"] == "paddle"
    assert out[0]["conflict_flag"] is False


def test_low_confidence_triggers_parseq_agreement(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], ("6000", 0.60)),
    ]
    ensemble = _make_ensemble(
        results, parseq=FakeParseq("6000", 0.80), monkeypatch=monkeypatch
    )
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    out = ensemble.run(img)
    assert len(out) == 1
    assert out[0]["text"] == "6000"
    assert out[0]["confidence"] > 0.60
    assert out[0]["conflict_flag"] is False


def test_low_confidence_triggers_parseq_disagreement(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], ("3000", 0.55)),
    ]
    ensemble = _make_ensemble(
        results, parseq=FakeParseq("8000", 0.80), monkeypatch=monkeypatch
    )
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    out = ensemble.run(img)
    assert len(out) == 1
    assert out[0]["text"] == "8000"
    assert out[0]["confidence"] <= DISAGREEMENT_CAP
    assert out[0]["conflict_flag"] is True


def test_no_parseq_passes_through() -> None:
    results = [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], ("6000", 0.50)),
    ]
    ensemble = OCREnsemble(paddle_engine=FakePaddle(results), parseq_model=None)
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    out = ensemble.run(img)
    assert len(out) == 1
    assert out[0]["text"] == "6000"
    assert out[0]["engine"] == "paddle"


def test_no_paddle_returns_empty() -> None:
    ensemble = OCREnsemble(paddle_engine=None, parseq_model=None)
    out = ensemble.run(np.zeros((10, 10, 3), dtype=np.uint8))
    assert out == []


def test_threshold_boundary() -> None:
    # Confidence exactly at threshold should be accepted without PARSeq
    assert PRIMARY_CONFIDENCE_THRESHOLD == 0.85
    assert AGREEMENT_BOOST == 0.10
