"""Pydantic schemas for project inputs.

The schemas are intentionally transport-neutral: the sizing engine receives these objects
whether they originated from JSON, a CLI, or a future application wrapper.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Dimensions(BaseModel):
    """Overall rectangular floor dimensions in feet."""

    length_ft: float = Field(gt=0)
    width_ft: float = Field(gt=0)


class LoadParameters(BaseModel):
    """Project-level load and material parameters for ASD gravity sizing."""

    dead_load_psf: float = Field(default=15.0, ge=0)
    live_load_psf: float = Field(default=40.0, ge=0)
    species: str = "Douglas Fir-Larch"
    grade: str = "No. 2"
    deflection_live_limit: int = Field(default=360, gt=0)
    deflection_total_limit: int = Field(default=240, gt=0)
    soil_bearing_psf: float = Field(default=1500.0, gt=0)
    service_condition: Literal["dry"] = "dry"
    temperature_f: float = 70.0
    incised: bool = False
    column_height_ft: float = Field(default=3.0, gt=0)
    beam_material_preference: Literal["any", "sawn", "glulam", "lvl_1.9E", "lvl_2.0E"] = "any"
    minimum_joist_nominal: str | None = None


class LayoutInput(BaseModel):
    """Structural layout parameters for one rectangular sample-plan option."""

    name: str
    layout_type: Literal["perimeter_support", "center_beam"]
    joist_span_ft: float = Field(gt=0)
    joist_spacing_in: float = Field(gt=0)
    description: str | None = None
    beam_span_ft: float | None = Field(default=None, gt=0)
    beam_total_length_ft: float | None = Field(default=None, gt=0)
    beam_tributary_width_ft: float | None = Field(default=None, gt=0)
    beam_span_config: Literal["simple", "two_span_equal", "three_span_equal"] = "simple"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize layout names so CLI layout selection is stable."""

        return value.strip().upper()


class HeaderInput(BaseModel):
    """Structured input for one door or window header sizing run."""

    rough_opening_ft: float = Field(gt=0)
    wall_thickness: Literal["2x4", "2x6"]
    header_load_condition: Literal["roof_only", "one_floor_above", "two_floors_above", "floor_only"]
    tributary_width_ft: float = Field(gt=0)
    bearing_length_in: float = Field(default=1.5, gt=0)
    material_preference: Literal["any", "sawn", "lvl_1.9E", "lvl_2.0E"] = "any"
    species: str = "Douglas Fir-Larch"
    grade: str = "No. 2"
    building_width_ft: float | None = Field(default=None, gt=0)
    ground_snow_load_psf: float | None = Field(default=None, ge=0)
    stories_supported: Literal["roof_only", "one_floor", "two_floors"] | None = None


class PlanInput(BaseModel):
    """Complete structured input for a rectangular residential floor sizing run."""

    model_config = ConfigDict(extra="forbid")

    project_name: str
    dimensions: Dimensions
    load_parameters: LoadParameters = Field(default_factory=LoadParameters)
    layouts: list[LayoutInput]

    def layout_by_name(self, name: str) -> LayoutInput:
        """Return the layout matching ``name`` or raise a clear validation error."""

        normalized = name.strip().upper()
        for layout in self.layouts:
            if layout.name == normalized:
                return layout
        available = ", ".join(layout.name for layout in self.layouts)
        raise ValueError(f"Unknown layout {name!r}; available layouts: {available}")
