"""Resolve ambiguous CV pipeline detections using Claude's vision API.

Sends floor-plan images with preliminary extraction results to Claude
for interpretation of uncertain regions.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from src.cv.reconciliation_budget import BudgetedLLMReconciler, ReconciliationBudget

logger = structlog.get_logger(__name__)


class AmbiguityResolver:
    """Use Claude vision to resolve uncertain detections."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = None
        if api_key:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=api_key)
            except ImportError:
                logger.warning("anthropic_not_installed")

    async def resolve_wall_ambiguity(
        self,
        image: np.ndarray,
        region_bbox: tuple[int, int, int, int],
        preliminary_classification: str,
        confidence: float,
    ) -> dict[str, Any]:
        """Ask Claude whether a low-confidence region is a wall.

        Returns ``{classification, confidence, reasoning}``.
        """
        if self._client is None:
            return {
                "classification": preliminary_classification,
                "confidence": confidence,
                "reasoning": "LLM not available — using original classification",
            }

        x1, y1, x2, y2 = region_bbox
        crop = image[y1:y2, x1:x2]
        b64 = self._encode_image(crop)

        prompt = (
            f"This region of a floor plan was classified as '{preliminary_classification}' "
            f"with {confidence:.0%} confidence. "
            "Looking at this image, is this: "
            "A) a structural wall, B) a partition wall, C) not a wall at all? "
            "Respond with JSON: {\"classification\": \"...\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"
        )

        message = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )

        try:
            return json.loads(message.content[0].text)
        except (json.JSONDecodeError, IndexError):
            return {
                "classification": preliminary_classification,
                "confidence": confidence,
                "reasoning": "Could not parse LLM response",
            }

    async def resolve_room_label(
        self,
        image: np.ndarray,
        room_polygon: list[list[float]],
        adjacent_labels: list[str],
    ) -> dict[str, Any]:
        """Ask Claude to classify an unlabelled room."""
        if self._client is None:
            return {"label": "UNDEFINED", "type": "UNDEFINED", "confidence": 0.5}

        b64 = self._encode_image(image)
        prompt = (
            f"This floor plan has an unlabelled room. "
            f"Adjacent rooms are: {adjacent_labels}. "
            f"The room polygon area suggests a {'small' if len(room_polygon) < 6 else 'large'} room. "
            "What type of room is this most likely? "
            "Respond with JSON: {\"label\": \"...\", \"type\": \"OFFICE|CORRIDOR|BATHROOM|...\", \"confidence\": 0.0-1.0}"
        )

        message = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )

        try:
            return json.loads(message.content[0].text)
        except (json.JSONDecodeError, IndexError):
            return {"label": "UNDEFINED", "type": "UNDEFINED", "confidence": 0.5}

    async def resolve_wall_dimensions_budgeted(
        self,
        walls_needing_llm: list[dict[str, Any]],
        total_walls: int,
        image: np.ndarray,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Batch-resolve wall dimensions under a per-plan LLM budget (Gap 9).

        Each entry in ``walls_needing_llm`` must have a ``bbox`` describing
        the region to inspect. Returns the resolved walls plus a
        ``ReconciliationStats`` dict.
        """
        budget = ReconciliationBudget()

        async def _call(wall: dict[str, Any]) -> tuple[float | None, float]:
            bbox = wall.get("bbox")
            if bbox is None:
                return None, 0.0
            x1, y1, x2, y2 = bbox
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                return None, 0.0
            result = await self.resolve_wall_dimension(crop)
            dim = result.get("dimension_mm")
            conf = result.get("confidence", 0.0)
            return dim, conf

        reconciler = BudgetedLLMReconciler(_call, budget=budget)
        resolved, stats = await reconciler.resolve_walls(walls_needing_llm, total_walls)
        return resolved, stats.to_dict()

    async def resolve_wall_dimension(self, crop: np.ndarray) -> dict[str, Any]:
        """Ask Claude to read the dimension value on a small cropped region."""
        if self._client is None:
            return {"dimension_mm": None, "confidence": 0.0, "reasoning": "LLM not available"}

        b64 = self._encode_image(crop)
        prompt = (
            "You are reading a single dimension label from an architectural floor plan. "
            "Return the dimension in millimeters. If no dimension is visible, return null. "
            "Respond with JSON: {\"dimension_mm\": number|null, \"confidence\": 0.0-1.0, "
            "\"reasoning\": string}"
        )

        message = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )

        try:
            return json.loads(message.content[0].text)
        except (json.JSONDecodeError, IndexError):
            return {"dimension_mm": None, "confidence": 0.0, "reasoning": "could not parse LLM response"}

    @staticmethod
    def _encode_image(image: np.ndarray) -> str:
        _, buffer = cv2.imencode(".png", image)
        return base64.b64encode(buffer).decode("utf-8")
