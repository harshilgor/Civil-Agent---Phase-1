"""Warning registry and construction helpers for Phase 3.

Every warning code is defined once in ``WARNING_CODES``. Engines raise warnings
by calling :func:`make_warning` — they MUST NOT construct ``Phase3Warning``
objects directly with ad-hoc strings.
"""

from __future__ import annotations

from typing import Optional

from .models.enums import WarningLevel
from .models.outputs import Phase3Warning

#: Code -> (level, message template, affected module, recommendation)
WARNING_CODES: dict[str, tuple[WarningLevel, str, str, str]] = {
    "P3W001": (
        WarningLevel.WARNING,
        "Building height exceeds simplified wind method limit of 60 m.",
        "wind",
        "Use ASCE 7-22 Chapter 27 full directional procedure or Chapter 28 MWFRS.",
    ),
    "P3W002": (
        WarningLevel.WARNING,
        "Irregular plan detected — Voronoi tributary cells may be inaccurate.",
        "tributary",
        "Review tributary polygons manually or provide an explicit tributary map.",
    ),
    "P3W003": (
        WarningLevel.ERROR,
        "ELF seismic procedure may not be permitted for this SDC and height.",
        "seismic",
        "Use Modal Response Spectrum Analysis per ASCE 7-22 Section 12.9.",
    ),
    "P3W004": (
        WarningLevel.INFO,
        "Seismic Ss/S1 values using conservative default — provide site-specific hazard data for accuracy.",
        "seismic",
        "Pull Ss and S1 from the ASCE 7 Hazard Tool for the exact site.",
    ),
    "P3W005": (
        WarningLevel.INFO,
        "Wind speed using conservative default — provide site-specific value for accuracy.",
        "wind",
        "Pull basic wind speed from ASCE 7-22 Figure 26.5-1A/B/C for the exact site.",
    ),
    "P3W006": (
        WarningLevel.WARNING,
        "Live load reduction not applied to storage occupancy (ASCE 7-22 Section 4.7.3).",
        "live_load",
        "This is expected behavior; verify occupancy classification is correct.",
    ),
    "P3W007": (
        WarningLevel.WARNING,
        "Tributary area fallback used (fewer than 3 supports on story).",
        "tributary",
        "Add additional support candidates or verify gravity framing is realistic.",
    ),
    "P3W008": (
        WarningLevel.ERROR,
        "Building code other than ASCE 7-22 requested — not supported in V1.",
        "inputs",
        "Resubmit with building_code='ASCE 7-22' or wait for multi-code support.",
    ),
    "P3W009": (
        WarningLevel.WARNING,
        "Multiple occupancy types detected — live load uses dominant occupancy per story.",
        "live_load",
        "Provide per-zone occupancy data for more precise live load mapping.",
    ),
    "P3W010": (
        WarningLevel.INFO,
        "Cladding weight estimated from perimeter — override if actual cladding system is known.",
        "dead_load",
        "Override assumption 'cladding_unit_weight' with actual curtain-wall unit weight.",
    ),
    "P3W011": (
        WarningLevel.WARNING,
        "Facade polygon missing or degenerate — cladding set to zero.",
        "dead_load",
        "Provide a non-degenerate facade polygon in the Building Graph.",
    ),
    "P3W012": (
        WarningLevel.WARNING,
        "Story has zero support candidates — tributary and member demands skipped.",
        "tributary",
        "Ensure Phase 2 produced support candidates for every gravity story.",
    ),
}


def make_warning(
    code: str,
    *,
    affected_element_ids: Optional[list[str]] = None,
    message_override: Optional[str] = None,
) -> Phase3Warning:
    """Build a ``Phase3Warning`` from a registered code.

    Args:
        code: Warning code (e.g. ``"P3W001"``).
        affected_element_ids: Optional list of element ids the warning applies to.
        message_override: Optional replacement message if more context is helpful.

    Raises:
        KeyError: If the code is not registered.
    """

    if code not in WARNING_CODES:
        raise KeyError(f"Unknown warning code: {code!r}")

    level, default_message, module, recommendation = WARNING_CODES[code]
    return Phase3Warning(
        code=code,
        level=level,
        message=message_override or default_message,
        affected_module=module,
        affected_element_ids=affected_element_ids or [],
        recommendation=recommendation,
    )
