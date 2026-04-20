from enum import Enum


class OccupancyType(str, Enum):
    OFFICE = "OFFICE"
    RESIDENTIAL = "RESIDENTIAL"
    MIXED_USE = "MIXED_USE"
    RETAIL = "RETAIL"
    INDUSTRIAL = "INDUSTRIAL"
    EDUCATIONAL = "EDUCATIONAL"
    HEALTHCARE = "HEALTHCARE"
    HOSPITALITY = "HOSPITALITY"
    PARKING = "PARKING"


class MaterialPreference(str, Enum):
    REINFORCED_CONCRETE = "REINFORCED_CONCRETE"
    STRUCTURAL_STEEL = "STRUCTURAL_STEEL"
    COMPOSITE = "COMPOSITE"
    TIMBER = "TIMBER"
    MASONRY = "MASONRY"


class WallType(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    PARTITION = "PARTITION"
    SHEAR_WALL = "SHEAR_WALL"
    RETAINING = "RETAINING"
    FACADE = "FACADE"


class OpeningType(str, Enum):
    DOOR = "DOOR"
    WINDOW = "WINDOW"
    GARAGE_DOOR = "GARAGE_DOOR"
    CURTAIN_WALL = "CURTAIN_WALL"


class CoreType(str, Enum):
    ELEVATOR_STAIR = "ELEVATOR_STAIR"
    STAIR_ONLY = "STAIR_ONLY"
    ELEVATOR_ONLY = "ELEVATOR_ONLY"
    SERVICE = "SERVICE"
    MEP = "MEP"


class RoomType(str, Enum):
    OFFICE = "OFFICE"
    CORRIDOR = "CORRIDOR"
    LOBBY = "LOBBY"
    BATHROOM = "BATHROOM"
    KITCHEN = "KITCHEN"
    BEDROOM = "BEDROOM"
    LIVING_ROOM = "LIVING_ROOM"
    STORAGE = "STORAGE"
    MECHANICAL = "MECHANICAL"
    STAIRWELL = "STAIRWELL"
    ELEVATOR = "ELEVATOR"
    CONFERENCE = "CONFERENCE"
    OUTDOOR = "OUTDOOR"
    UNDEFINED = "UNDEFINED"


class InputSource(str, Enum):
    STRUCTURED_FORM = "STRUCTURED_FORM"
    DXF_FILE = "DXF_FILE"
    DWG_FILE = "DWG_FILE"
    IFC_FILE = "IFC_FILE"
    FLOOR_PLAN_IMAGE = "FLOOR_PLAN_IMAGE"


class RoofType(str, Enum):
    FLAT = "FLAT"
    PITCHED = "PITCHED"
    HIPPED = "HIPPED"
    GABLE = "GABLE"


class BuildingType(str, Enum):
    """High-level building classification inferred by the VLM gap-filler.

    Distinct from :class:`OccupancyType` (user-supplied program label) — this
    is the model's read of the *physical* building family and drives downstream
    heuristics (e.g. residential models use the CubiCasa hourglass adapter,
    commercial floor plates use the SMP U-Net path).
    """

    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    INSTITUTIONAL = "INSTITUTIONAL"
    MIXED_USE = "MIXED_USE"
    UNKNOWN = "UNKNOWN"


class DetectorSource(str, Enum):
    """Which producer is responsible for an element in the Building Graph.

    Recorded on every :class:`~src.schema.provenance.ProvenanceRecord` so that
    downstream stages (and reviewers) can audit where each wall, room, or
    opening originated.
    """

    STRUCTURED_FORM = "STRUCTURED_FORM"
    CAD_DIRECT = "CAD_DIRECT"
    IFC_DIRECT = "IFC_DIRECT"
    CUBICASA_HG = "CUBICASA_HG"
    SMP_UNET = "SMP_UNET"
    YOLO_SEG = "YOLO_SEG"
    SYMBOL_DETECTOR = "SYMBOL_DETECTOR"
    VLM_GAP_FILL = "VLM_GAP_FILL"
    HEURISTIC = "HEURISTIC"
    USER_OVERRIDE = "USER_OVERRIDE"


class ConfidenceLevel(str, Enum):
    """Qualitative confidence bucket derived from a numeric 0.0–1.0 score.

    Shared across Phase 1 (Building Graph) and Phase 3 (load assumptions).
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence_to_level(score: float) -> ConfidenceLevel:
    """Convert a 0.0–1.0 numeric confidence into a :class:`ConfidenceLevel`.

    Buckets follow the standard ASCE-aligned thresholds: ``>= 0.85`` is HIGH,
    ``>= 0.6`` is MEDIUM, otherwise LOW.
    """

    if score >= 0.85:
        return ConfidenceLevel.HIGH
    if score >= 0.60:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW
