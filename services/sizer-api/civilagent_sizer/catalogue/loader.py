"""Catalogue YAML loading functions.

The loader keeps catalogue data out of calculation code. It returns Pydantic models so
transcription errors fail early during tests or CLI execution.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, TypeVar

import yaml

from civilagent_sizer.catalogue.models import (
    DesignValueEntry,
    GlulamDesignValueEntry,
    LVLDesignValueEntry,
    SectionEntry,
)

# Members above this utilisation are upsized to the next catalogue size.
# The 0.90 threshold is a Civil Agent design margin, not an NDS code requirement.
# Engineers may override this threshold.
CATALOGUE_UPSIZE_THRESHOLD = 0.90

_T = TypeVar("_T")


@dataclass(frozen=True)
class CatalogueSelection:
    """Catalogue selection result including auto-upsize metadata."""

    selected: _T
    auto_upsized: bool
    auto_upsize_reason: str
    minimum_passing_member: str


def get_data_root() -> Path:
    """Return the project data directory containing YAML catalogue files."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate project data directory")


@cache
def load_yaml(relative_path: str) -> dict[str, Any]:
    """Load a YAML file below ``data/`` and return its raw mapping."""

    path = get_data_root() / relative_path
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


@cache
def list_sections(
    material_type: str | None = None, family: str | None = None
) -> tuple[SectionEntry, ...]:
    """List section entries, optionally filtered by material type and family."""

    raw_sections = []
    for relative_path in (
        "sections/sawn_lumber.yaml",
        "sections/glulam.yaml",
        "sections/lvl_sections.yaml",
        "sections/header_sections.yaml",
    ):
        raw_sections.extend(load_yaml(relative_path)["sections"])
    sections = [SectionEntry.model_validate(item) for item in raw_sections]
    if material_type is not None:
        sections = [item for item in sections if item.material_type == material_type]
    if family is not None:
        sections = [item for item in sections if item.family == family]
    return tuple(sections)


def get_section(nominal: str, material_type: str | None = None) -> SectionEntry:
    """Return a section by nominal size and optional material type."""

    for section in list_sections(material_type=material_type):
        if section.nominal == nominal:
            return section
    raise KeyError(f"Section {nominal!r} not found")


@cache
def _dimension_lumber_entries() -> tuple[DesignValueEntry, ...]:
    return tuple(
        DesignValueEntry.model_validate(item)
        for item in load_yaml("species_grades/dimension_lumber.yaml")["entries"]
    )


@cache
def _timber_entries() -> tuple[DesignValueEntry, ...]:
    return tuple(
        DesignValueEntry.model_validate(item)
        for item in load_yaml("species_grades/timbers.yaml")["entries"]
    )


@cache
def _glulam_entries() -> tuple[GlulamDesignValueEntry, ...]:
    return tuple(
        GlulamDesignValueEntry.model_validate(item)
        for item in load_yaml("species_grades/glulam.yaml")["entries"]
    )


@cache
def _lvl_entries() -> tuple[LVLDesignValueEntry, ...]:
    return tuple(
        LVLDesignValueEntry.model_validate(item)
        for item in load_yaml("species_grades/lvl_trus_joist.yaml")["entries"]
    )


def get_design_values(species: str, grade: str, nominal: str) -> DesignValueEntry:
    """Return dimension-lumber reference design values for a species, grade, and size."""

    exact_matches = [
        entry
        for entry in _dimension_lumber_entries()
        if entry.species == species and entry.grade == grade and entry.nominal == nominal
    ]
    if exact_matches:
        return exact_matches[0]

    base_matches = [
        entry
        for entry in _dimension_lumber_entries()
        if entry.species == species and entry.grade == grade and entry.scope == "base"
    ]
    if base_matches:
        return base_matches[0]

    raise KeyError(f"No dimension lumber values for {species} {grade} {nominal}")


def get_timber_design_values(species: str, grade: str, category: str) -> DesignValueEntry:
    """Return timber reference design values by use category."""

    for entry in _timber_entries():
        if entry.species == species and entry.grade == grade and entry.category == category:
            return entry
    raise KeyError(f"No timber values for {species} {grade} {category}")


def get_glulam_design_values(grade: str = "24F-V4 DF/DF") -> GlulamDesignValueEntry:
    """Return glulam reference design values for a named glulam combination."""

    for entry in _glulam_entries():
        if entry.grade == grade:
            return entry
    raise KeyError(f"No glulam values for {grade}")


def get_lvl_design_values(grade: str) -> LVLDesignValueEntry:
    """Return manufacturer reference design values for a named LVL grade."""

    for entry in _lvl_entries():
        if entry.grade == grade:
            return entry
    raise KeyError(f"No LVL values for {grade}")


def select_catalogue_result(
    passing_results: Sequence[_T],
    *,
    utilization_getter: Callable[[_T], float],
    designation_getter: Callable[[_T], str],
    max_utilisation_threshold: float = CATALOGUE_UPSIZE_THRESHOLD,
) -> CatalogueSelection:
    """Return the selected catalogue result with auto-upsize metadata."""

    if not passing_results:
        raise ValueError("At least one passing catalogue result is required")

    minimum_passing = passing_results[0]
    minimum_utilization = utilization_getter(minimum_passing)
    if minimum_utilization <= max_utilisation_threshold or len(passing_results) == 1:
        return CatalogueSelection(
            selected=minimum_passing,
            auto_upsized=False,
            auto_upsize_reason="",
            minimum_passing_member="",
        )

    return CatalogueSelection(
        selected=passing_results[1],
        auto_upsized=True,
        auto_upsize_reason=(
            "Minimum passing member governing utilisation "
            f"{minimum_utilization:.2f} exceeded {max_utilisation_threshold:.2f} threshold"
        ),
        minimum_passing_member=designation_getter(minimum_passing),
    )
