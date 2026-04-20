"""Enumerations used across Phase 3 models and engines."""

from __future__ import annotations

from enum import Enum


class OccupancyCategory(str, Enum):
    """Occupancy classifications per ASCE 7-22 Table 4.3-1 (condensed)."""

    OFFICE = "office"
    RESIDENTIAL = "residential"
    RETAIL = "retail"
    STORAGE_LIGHT = "storage_light"
    STORAGE_HEAVY = "storage_heavy"
    ASSEMBLY = "assembly"
    MECHANICAL = "mechanical"
    ROOF_ACCESSIBLE = "roof_accessible"
    ROOF_INACCESSIBLE = "roof_inaccessible"
    PARKING = "parking"
    CORRIDOR = "corridor"
    LOBBY = "lobby"


class MaterialFamily(str, Enum):
    """Primary structural material family.

    V1 supports reinforced concrete and structural steel only.
    """

    REINFORCED_CONCRETE = "reinforced_concrete"
    STRUCTURAL_STEEL = "structural_steel"


class RiskCategory(str, Enum):
    """Risk category per ASCE 7-22 Table 1.5-1."""

    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class SeismicDesignCategory(str, Enum):
    """Seismic Design Category per ASCE 7-22 Tables 11.6-1 and 11.6-2."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class ExposureCategory(str, Enum):
    """Wind exposure category per ASCE 7-22 Section 26.7."""

    B = "B"
    C = "C"
    D = "D"


class LoadCombinationType(str, Enum):
    """LRFD strength load combinations per ASCE 7-22 Section 2.3.1.

    Values are human-readable labels, used for display and serialization.
    """

    LRFD_1 = "1.4D"
    LRFD_2 = "1.2D + 1.6L + 0.5Lr"
    LRFD_3 = "1.2D + 1.6Lr + (L or 0.5W)"
    LRFD_4 = "1.2D + 1.0W + L + 0.5Lr"
    LRFD_5 = "0.9D + 1.0W"
    LRFD_6 = "1.2D + 1.0E + L"
    LRFD_7 = "0.9D + 1.0E"


class ConfidenceLevel(str, Enum):
    """Qualitative confidence bucket derived from a numeric 0.0–1.0 score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WarningLevel(str, Enum):
    """Severity of a Phase 3 warning."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
