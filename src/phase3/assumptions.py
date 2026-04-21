"""AssumptionBuilder — central factory for ``AssumptionRecord`` objects.

All engines MUST construct assumptions through this builder. Creating
``AssumptionRecord`` instances directly inside engine modules is forbidden
(there is no compiler check — this is enforced by code review and the
assumption-coverage tests).
"""

from __future__ import annotations

from typing import Any, Optional

from .models.assumptions import AssumptionRecord
from .models.enums import ConfidenceLevel
from .models.inputs import OverrideEntry
from .models.outputs import AssumptionRegister


class AssumptionBuilder:
    """Accumulates ``AssumptionRecord`` objects and produces an ``AssumptionRegister``."""

    #: Threshold above which an assumption is bucketed as HIGH confidence.
    HIGH_CONFIDENCE_THRESHOLD: float = 0.85
    #: Threshold above which an assumption is bucketed as MEDIUM confidence.
    MEDIUM_CONFIDENCE_THRESHOLD: float = 0.60

    def __init__(self) -> None:
        self._records: dict[str, AssumptionRecord] = {}

    def add(
        self,
        *,
        id: str,
        name: str,
        value: Any,
        unit: Optional[str],
        source: str,
        confidence: float,
        rationale: str,
        overrideable: bool,
        affects_modules: list[str],
    ) -> AssumptionRecord:
        """Create and register a new ``AssumptionRecord``.

        Args:
            id: Unique snake_case identifier.
            name: Human-readable short name.
            value: The assumed value.
            unit: SI unit string or ``None``.
            source: Code or derivation reference.
            confidence: Numeric confidence 0.0–1.0.
            rationale: Plain-English justification.
            overrideable: Whether the user may override.
            affects_modules: Downstream module names.

        Returns:
            The created ``AssumptionRecord``.

        Raises:
            ValueError: If an assumption with the same ``id`` already exists.
        """

        if id in self._records:
            raise ValueError(
                f"Duplicate assumption id '{id}'. Each assumption must be recorded once."
            )

        record = AssumptionRecord(
            id=id,
            name=name,
            value=value,
            unit=unit,
            source=source,
            confidence=confidence,
            confidence_level=self._confidence_level(confidence),
            rationale=rationale,
            overrideable=overrideable,
            affects_modules=affects_modules,
        )
        self._records[id] = record
        return record

    def has(self, assumption_id: str) -> bool:
        """Return whether an assumption with the given id already exists."""

        return assumption_id in self._records

    def get(self, assumption_id: str) -> AssumptionRecord:
        """Return the assumption with the given id.

        Raises:
            KeyError: If no such assumption has been registered.
        """

        return self._records[assumption_id]

    def effective_value(self, assumption_id: str) -> Any:
        """Return the effective (possibly overridden) value of an assumption."""

        return self._records[assumption_id].effective_value

    def apply_overrides(self, overrides: list[OverrideEntry]) -> None:
        """Apply user overrides in-place to the registered assumptions.

        Raises:
            ValueError: If any override targets an unknown or non-overrideable id.
        """

        for override in overrides:
            if override.assumption_id not in self._records:
                raise ValueError(
                    f"Unknown assumption id: '{override.assumption_id}'"
                )
            record = self._records[override.assumption_id]
            if not record.overrideable:
                raise ValueError(
                    f"Assumption '{override.assumption_id}' is not overrideable."
                )
            record.was_overridden = True
            record.override_value = override.new_value
            record.override_source = override.provided_by

    def build_register(self) -> AssumptionRegister:
        """Snapshot the current state into an immutable ``AssumptionRegister``."""

        records = list(self._records.values())
        return AssumptionRegister(
            total_count=len(records),
            overridden_count=sum(1 for r in records if r.was_overridden),
            low_confidence_count=sum(1 for r in records if r.confidence < self.MEDIUM_CONFIDENCE_THRESHOLD),
            records=records,
        )

    @classmethod
    def _confidence_level(cls, confidence: float) -> ConfidenceLevel:
        """Map a numeric confidence to the qualitative bucket."""

        if confidence > cls.HIGH_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.HIGH
        if confidence >= cls.MEDIUM_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
