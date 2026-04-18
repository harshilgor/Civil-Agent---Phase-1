"""Parse natural language building descriptions into StructuredInputRequest.

Uses Claude (Anthropic API) to interpret free-text descriptions and produce
validated structured input.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.schema.input_models import StructuredInputRequest

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a structural engineering assistant that converts natural language building descriptions into structured JSON parameters.

Given a building description, extract the following parameters (all dimensions in millimeters):

Required fields:
- project_name: string (infer from context or use "Unnamed Project")
- location: {lat, lng, city, state, country} (look up coordinates for the city)
- length_mm: building length in X direction (convert from meters/feet if needed)
- width_mm: building width in Y direction
- num_stories: integer >= 1
- occupancy_type: one of OFFICE, RESIDENTIAL, MIXED_USE, RETAIL, INDUSTRIAL, EDUCATIONAL, HEALTHCARE, HOSPITALITY, PARKING
- material_preference: one of REINFORCED_CONCRETE, STRUCTURAL_STEEL, COMPOSITE, TIMBER, MASONRY

Optional fields (use reasonable defaults if not specified):
- floor_to_floor_mm: typical storey height (default: 3900 for office, 3200 for residential)
- ground_floor_height_mm: often taller (4500 for lobbies)
- preferred_bay_x_mm: target bay span in X (default: 8000)
- preferred_bay_y_mm: target bay span in Y (default: 8000)
- min_bay_mm: minimum bay (default: 4000)
- max_bay_mm: maximum bay (default: 15000)
- building_code: default "IBC 2021"
- optimization_hints: list of strings like ["minimize_cost", "fewer_columns", "maximize_span"]

Interpretation rules:
- "minimize columns" / "open plan" → larger preferred_bay (10000-12000)
- "cost effective" / "economical" → REINFORCED_CONCRETE, moderate bays (7000-9000)
- "long span" → STRUCTURAL_STEEL, larger max_bay
- Convert meters to mm (multiply by 1000), feet to mm (multiply by 304.8)

Respond with ONLY valid JSON matching the StructuredInputRequest schema.
Also include an "assumptions" key listing any assumptions you made."""


class IntentParser:
    """Parse natural language building descriptions into structured input."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = None
        if api_key:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=api_key)
                logger.info("intent_parser_ready")
            except ImportError:
                logger.warning("anthropic_not_installed")

    async def parse(self, description: str) -> tuple[StructuredInputRequest, list[str]]:
        """Convert *description* to a ``StructuredInputRequest``.

        Returns ``(request, assumptions_made)``.

        Raises ``ValueError`` if the description cannot be parsed.
        """
        if self._client is None:
            raise RuntimeError(
                "Anthropic API client not configured. "
                "Set ANTHROPIC_API_KEY in environment."
            )

        message = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": description},
            ],
        )

        response_text = message.content[0].text
        logger.debug("llm_response", text=response_text[:500])

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        assumptions = data.pop("assumptions", [])
        request = StructuredInputRequest(**data)
        logger.info("intent_parsed", project=request.project_name, stories=request.num_stories)
        return request, assumptions
