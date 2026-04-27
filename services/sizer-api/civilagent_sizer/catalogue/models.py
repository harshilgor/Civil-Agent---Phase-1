"""Pydantic models for catalogue YAML entries."""

from pydantic import BaseModel, Field


class SectionEntry(BaseModel):
    """Geometric section properties for sawn lumber or glulam."""

    nominal: str
    material_type: str
    family: str
    actual_width_in: float = Field(gt=0)
    actual_depth_in: float = Field(gt=0)
    area_in2: float = Field(gt=0)
    sx_in3: float = Field(gt=0)
    ix_in4: float = Field(gt=0)
    sy_in3: float | None = None
    iy_in4: float | None = None
    laminations: int | None = None
    source: str
    confidence: str
    notes: str | None = None


class DesignValues(BaseModel):
    """Reference design values for a wood material entry."""

    fb_psi: float
    ft_psi: float
    fv_psi: float
    fc_perp_psi: float
    fc_psi: float
    e_psi: float
    emin_psi: float


class DesignValueEntry(BaseModel):
    """A species/grade design value row from a catalogue file."""

    species: str
    grade: str
    values: DesignValues
    source: str
    confidence: str
    scope: str | None = None
    nominal: str | None = None
    category: str | None = None
    notes: str | None = None


class GlulamDesignValues(BaseModel):
    """Reference design values for a glulam combination."""

    fbx_positive_psi: float
    fbx_negative_psi: float
    fvx_psi: float
    fc_perp_x_psi: float
    fc_psi: float
    ft_psi: float
    ex_psi: float
    ey_psi: float
    ex_min_psi: float


class GlulamDesignValueEntry(BaseModel):
    """Glulam grade row from the catalogue."""

    grade: str
    species: str
    values: GlulamDesignValues
    source: str
    confidence: str
    notes: str | None = None


class LVLDesignValueEntry(BaseModel):
    """Manufacturer-published LVL design value row."""

    product: str
    material_type: str
    grade: str
    values: DesignValues
    source: str
    confidence: str
    notes: str
