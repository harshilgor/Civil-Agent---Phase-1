"""Phase 2 Structural Abstraction Engine.

Converts a Phase 1 ``BuildingGraph`` into a Phase 2
``StructuralDesignGraph`` — the searchable design space consumed by later
optimization and system-selection phases.
"""

from src.structural.engine import StructuralEngine

__all__ = ["StructuralEngine"]
