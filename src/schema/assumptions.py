"""Shared assumption schema — used by Phase 1 (Building Graph), Phase 3
(Load & Assumption Engine), and any future stage that needs to record an
auditable engineering assumption.

No silent assumptions are permitted anywhere in the agent: every numeric
constant, code-table lookup, material property, geometry inference, or
engineering judgement MUST be persisted as an :class:`AssumptionRecord` so
the human reviewer can audit, accept, or override it.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .enums import ConfidenceLevel, confidence_to_level


class AssumptionRecord(BaseModel):
    """A single auditable assumption made anywhere in the pipeline.

    Attributes:
        id: Unique snake_case identifier (stable across runs).
        name: Human-readable short name.
        value: The assumed value (numeric, string, or bool).
        unit: SI unit string, or ``None`` for dimensionless / categorical.
        source: Code reference or derivation, e.g. ``"ASCE 7-22 Table 4.3-1"``
            or ``"Phase 1 / VLM gap-fill / wall thickness default"``.
        confidence: Numeric confidence in the assumption (0.0–1.0).
        confidence_level: Bucketed confidence (HIGH / MEDIUM / LOW).
        rationale: Plain-English reason for picking this value.
        overrideable: Whether the user can override the assumption.
        was_overridden: True if an override has been applied.
        override_value: Value supplied by the override.
        override_source: Who/what provided the override.
        affects_modules: Downstream modules impacted by this assumption.
    """

    id: str = Field(..., description="Unique snake_case identifier")
    name: str = Field(..., description="Human-readable name")
    value: Any = Field(..., description="The assumed value (numeric/str/bool)")
    unit: Optional[str] = Field(
        default=None,
        description="SI unit string (e.g. 'kN/m^2', 'kPa', 'm/s', 'dimensionless')",
    )
    source: str = Field(..., description="Code reference or derivation")
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    rationale: str = Field(..., description="Why this value was chosen")
    overrideable: bool = Field(..., description="Whether the user can override")
    was_overridden: bool = Field(default=False)
    override_value: Optional[Any] = Field(default=None)
    override_source: Optional[str] = Field(default=None)
    affects_modules: list[str] = Field(default_factory=list)

    @property
    def effective_value(self) -> Any:
        """Return the override value if present, otherwise the original value."""

        return self.override_value if self.was_overridden else self.value

    @classmethod
    def quick(
        cls,
        *,
        id: str,
        name: str,
        value: Any,
        source: str,
        rationale: str,
        confidence: float = 0.8,
        unit: Optional[str] = None,
        overrideable: bool = True,
        affects_modules: Optional[list[str]] = None,
    ) -> "AssumptionRecord":
        """Convenience factory that auto-derives ``confidence_level``.

        Use from Phase 1 detectors and gap-fillers when constructing routine
        assumptions; Phase 3 retains its richer ``AssumptionBuilder``.
        """

        return cls(
            id=id,
            name=name,
            value=value,
            unit=unit,
            source=source,
            confidence=confidence,
            confidence_level=confidence_to_level(confidence),
            rationale=rationale,
            overrideable=overrideable,
            affects_modules=affects_modules or [],
        )
