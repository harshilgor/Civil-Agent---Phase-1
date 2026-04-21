"""Stage-2 VLM classifier — classify a floor-plan image into a :class:`BuildingType`.

Channel C runs in three stages:

* Stage 1 (:mod:`src.cv.preprocessor`): normalise the uploaded image for
  a multimodal-LLM round-trip — EXIF orientation, DPI-aware downscale,
  PNG encoding.
* Stage 2 (this module): send the normalised image to Claude vision and
  ask for a building-family classification (``COMMERCIAL``,
  ``RESIDENTIAL``, ``INSTITUTIONAL``, …).  The output drives manifest
  selection — Stage 3+ loads a building-type-appropriate wall segmenter
  based on this call.
* Stage 3+: perception pipeline proper (Step 9).

This file is deliberately narrow: one class with one method.  All the
prompt engineering and JSON-parsing lives here so the rest of the code
base can treat ``BuildingTypeClassifier`` as a black box that maps
bytes → :class:`ClassificationResult`.

Graceful degradation: if no API key is configured (or ``anthropic`` is
not installed), every call returns :data:`UNAVAILABLE_RESULT` — a
low-confidence ``BuildingType.UNKNOWN`` — so the worker task can
continue with the fixed occupancy→building-type fallback instead of
aborting.  This is the same contract
:class:`src.llm.ambiguity_resolver.AmbiguityResolver` uses and keeps CI
green without an API key.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

import structlog

from src.schema.enums import BuildingType

logger = structlog.get_logger(__name__)


# The Claude model used for vision classification.  Kept as a module
# constant so it can be monkeypatched in tests and stamped on every
# provenance record.
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Maximum output tokens for a classification response — Claude's answer
# is a small JSON object so 512 is more than enough and keeps the
# billing floor low.
_MAX_TOKENS = 512


_SYSTEM_PROMPT = (
    "You are a civil engineering assistant classifying architectural "
    "floor plans.  You will be shown a single floor plan image.  Your "
    "job is to decide which of the following building families it "
    "most plausibly belongs to: RESIDENTIAL, COMMERCIAL, INDUSTRIAL, "
    "INSTITUTIONAL, MIXED_USE, or UNKNOWN.\n"
    "\n"
    "Guidelines:\n"
    "  - RESIDENTIAL: apartments, condos, single-family homes, town "
    "    houses, dormitories.\n"
    "  - COMMERCIAL: offices, retail stores, hotels, restaurants, "
    "    banks, co-working floors.\n"
    "  - INDUSTRIAL: warehouses, factories, production halls, data "
    "    centres, workshops.\n"
    "  - INSTITUTIONAL: schools, hospitals, government buildings, "
    "    libraries, museums.\n"
    "  - MIXED_USE: clearly combines two or more of the above at a "
    "    single floor-plate scale (e.g. retail + apartments).\n"
    "  - UNKNOWN: reserved for when you genuinely cannot tell from the "
    "    image alone (blank plan, illegible scan, sheet of notation).\n"
    "\n"
    "Return ONLY valid JSON matching this schema, no prose:\n"
    "  {\n"
    "    \"building_type\": \"<one of the 6 labels above>\",\n"
    "    \"confidence\": <float in [0.0, 1.0]>,\n"
    "    \"rationale\": \"<one-sentence justification>\"\n"
    "  }"
)


@dataclass(frozen=True)
class ClassificationResult:
    """Output of :meth:`BuildingTypeClassifier.classify`.

    ``raw_response`` carries the verbatim JSON text the VLM returned
    so downstream auditing (and debugging of parse failures) has
    something to work with.  ``model_id`` is the exact Claude model
    string used so the manifest-selection audit trail can tie a
    classification back to a specific inference.
    """

    building_type: BuildingType
    confidence: float
    rationale: str
    model_id: str
    raw_response: Optional[str] = None
    is_fallback: bool = False


UNAVAILABLE_RESULT = ClassificationResult(
    building_type=BuildingType.UNKNOWN,
    confidence=0.0,
    rationale=(
        "VLM classifier unavailable — no API key configured or the "
        "``anthropic`` SDK is not installed.  Downstream consumers "
        "should fall back to the occupancy-derived BuildingType map."
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    raw_response=None,
    is_fallback=True,
)


class BuildingTypeClassifier:
    """Classify floor-plan images via Claude vision.

    The constructor mirrors :class:`AmbiguityResolver`: if no API key is
    available (and no pre-built ``client`` is injected), :attr:`client`
    stays ``None`` and every call returns :data:`UNAVAILABLE_RESULT`.
    Tests inject a :class:`unittest.mock.MagicMock` via ``client=`` to
    avoid touching the real API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        client: Any = None,
        model: str = DEFAULT_CLAUDE_MODEL,
    ) -> None:
        self.model = model
        self._client = client

        if self._client is None and api_key:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=api_key)
            except ImportError:  # pragma: no cover - depends on env.
                logger.warning("anthropic_not_installed")
                self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def classify(self, png_bytes: bytes) -> ClassificationResult:
        """Classify a single PNG image.

        *png_bytes* must already be the output of
        :meth:`src.cv.preprocessor.Preprocessor.prepare_for_vlm` — we do
        not re-encode here; the caller is responsible for orientation,
        sizing, and encoding.
        """

        if self._client is None:
            return UNAVAILABLE_RESULT

        b64 = base64.b64encode(png_bytes).decode("utf-8")
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Classify this floor plan and return JSON only."
                                ),
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:  # network / API / auth / rate-limit
            logger.error("vlm_classify_api_failed", error=str(exc))
            return ClassificationResult(
                building_type=BuildingType.UNKNOWN,
                confidence=0.0,
                rationale=f"VLM call failed: {exc}",
                model_id=self.model,
                raw_response=None,
                is_fallback=True,
            )

        raw_text = _extract_text(message)
        if raw_text is None:
            logger.error(
                "vlm_classify_empty_response", message=repr(message)
            )
            return ClassificationResult(
                building_type=BuildingType.UNKNOWN,
                confidence=0.0,
                rationale="VLM returned no text content",
                model_id=self.model,
                raw_response=None,
                is_fallback=True,
            )

        parsed = _parse_classification_json(raw_text)
        if parsed is None:
            logger.error(
                "vlm_classify_parse_failed",
                raw=_safe_truncate(raw_text, 512),
            )
            return ClassificationResult(
                building_type=BuildingType.UNKNOWN,
                confidence=0.0,
                rationale=(
                    "VLM response could not be parsed as JSON; falling "
                    "back to UNKNOWN."
                ),
                model_id=self.model,
                raw_response=raw_text,
                is_fallback=True,
            )

        return ClassificationResult(
            building_type=parsed["building_type"],
            confidence=parsed["confidence"],
            rationale=parsed["rationale"],
            model_id=self.model,
            raw_response=raw_text,
            is_fallback=False,
        )


# ---------------------------------------------------------------------------
# Parsing helpers.  Kept module-level (not methods) so they're trivially
# unit-testable without a classifier instance.
# ---------------------------------------------------------------------------


def _extract_text(message: Any) -> Optional[str]:
    """Pull the first text block out of an Anthropic message object.

    The real SDK returns a ``Message`` with ``.content`` = list of
    content blocks; the mock pattern tests use emulates the same shape.
    """

    content = getattr(message, "content", None)
    if not content:
        return None
    try:
        first = content[0]
    except (TypeError, IndexError):
        return None
    text = getattr(first, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    # Some mocks use a dict shape rather than an object.
    if isinstance(first, dict) and isinstance(first.get("text"), str):
        return first["text"]
    return None


def _parse_classification_json(raw: str) -> Optional[dict]:
    """Parse a Claude classification JSON blob into a clean dict.

    Returns ``None`` on any structural problem.  Accepts JSON that is
    either bare or wrapped in an opening ``{`` / trailing ``}`` inside
    some prose preamble (Claude occasionally chats briefly before the
    JSON even with a strict instruction).
    """

    candidate = _best_json_object(raw)
    if candidate is None:
        return None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    try:
        bt = BuildingType(str(data["building_type"]).upper().strip())
    except (KeyError, ValueError):
        return None

    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None
    # Clamp, don't reject — Claude occasionally emits 0-100 scale.
    if conf > 1.0:
        conf = conf / 100.0 if conf <= 100.0 else 1.0
    conf = max(0.0, min(1.0, conf))

    rationale = str(data.get("rationale", "")).strip() or "(no rationale provided)"

    return {
        "building_type": bt,
        "confidence": conf,
        "rationale": rationale,
    }


def _best_json_object(raw: str) -> Optional[str]:
    """Best-effort extraction of the first balanced ``{...}`` block."""

    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return None


def _safe_truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


__all__ = [
    "BuildingTypeClassifier",
    "ClassificationResult",
    "DEFAULT_CLAUDE_MODEL",
    "UNAVAILABLE_RESULT",
]
