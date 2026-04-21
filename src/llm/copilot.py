"""Main LLM copilot interface.

Combines intent parsing and ambiguity resolution into a single high-level
API for the application layer.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.config import settings
from src.core.graph_builder import GraphBuilder
from src.schema.building_graph import BuildingGraph
from src.schema.input_models import StructuredInputRequest

from .ambiguity_resolver import AmbiguityResolver
from .intent_parser import IntentParser

logger = structlog.get_logger(__name__)


class Copilot:
    """High-level LLM copilot for the Building Understanding Layer."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        self.intent_parser = IntentParser(api_key=key)
        self.ambiguity_resolver = AmbiguityResolver(api_key=key)
        self.graph_builder = GraphBuilder()

    async def natural_language_to_graph(self, description: str) -> BuildingGraph:
        """Convert a natural language building description to a BuildingGraph.

        Example: "8-story office in SF, 40x25m, reinforced concrete"
        """
        request, assumptions = await self.intent_parser.parse(description)
        graph = self.graph_builder.from_structured_input(request)

        # Add the LLM's assumptions to metadata
        existing = list(graph.metadata.assumptions_made)
        existing.extend([f"[LLM] {a}" for a in assumptions])
        graph = graph.model_copy(
            update={"metadata": graph.metadata.model_copy(update={"assumptions_made": existing})}
        )

        logger.info("copilot_graph_built", stories=len(graph.stories))
        return graph
