"""Abstract base for vendor model adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.schemas import UnifiedPerceptionOutput


class BasePerceptionAdapter(ABC):
    """load(), predict(), to_unified_output()."""

    @abstractmethod
    def load(self, weights_path: str | None = None) -> None:
        """Load weights and build model graph."""

    @abstractmethod
    def predict(self, *args: Any, **kwargs: Any) -> Any:
        """Run forward pass."""

    @abstractmethod
    def to_unified_output(self, raw: Any) -> UnifiedPerceptionOutput:
        """Convert raw tensors to shared schema."""
