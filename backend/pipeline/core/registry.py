"""Model registry: name → adapter class."""

from __future__ import annotations

from typing import Callable, Type

from ..stage1_perception.base_adapter import BasePerceptionAdapter


class ModelRegistry:
    """Maps logical model names to adapter classes."""

    def __init__(self) -> None:
        self._adapters: dict[str, Type[BasePerceptionAdapter]] = {}

    def register(self, name: str) -> Callable[[Type[BasePerceptionAdapter]], Type[BasePerceptionAdapter]]:
        def decorator(cls: Type[BasePerceptionAdapter]) -> Type[BasePerceptionAdapter]:
            self._adapters[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> Type[BasePerceptionAdapter]:
        if name not in self._adapters:
            raise KeyError(f"Unknown model adapter: {name}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())


registry = ModelRegistry()
