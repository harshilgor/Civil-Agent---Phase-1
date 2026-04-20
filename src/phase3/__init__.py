"""Phase 3 — Load & Assumption Engine.

Consumes the Phase 1 Building Graph and Phase 2 Structural Design Graph, and
produces a ``DesignLoadModel`` + ``AssumptionRegister`` per ASCE 7-22. Every
assumption is recorded; every computed value is traceable to a code provision
or an explicit engineering rationale.
"""

from .phase3_service import Phase3Service

__all__ = ["Phase3Service"]
__version__ = "1.0.0"
