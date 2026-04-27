"""Shared helpers for member sizing traces."""

from collections.abc import Sequence

from civilagent_sizer.catalogue.models import DesignValueEntry, SectionEntry
from civilagent_sizer.trace.models import (
    CalculationTrace,
    CodeCheck,
    MaterialSpec,
    MemberResult,
    SourceValue,
)


def nominal_sort_key(nominal: str) -> tuple[float, float]:
    """Sort nominal sizes by width then depth, accepting values like ``2x10``."""

    left, right = nominal.lower().split("x", maxsplit=1)
    return (float(left), float(right))


def section_source_values(section: SectionEntry) -> list[SourceValue]:
    """Return traceable section properties for a selected catalogue section."""

    return [
        SourceValue(
            name="actual_width",
            value=section.actual_width_in,
            unit="in",
            source=section.source,
            confidence=section.confidence,
        ),
        SourceValue(
            name="actual_depth",
            value=section.actual_depth_in,
            unit="in",
            source=section.source,
            confidence=section.confidence,
        ),
        SourceValue(
            name="area",
            value=section.area_in2,
            unit="in^2",
            source=section.source,
            confidence=section.confidence,
        ),
        SourceValue(
            name="Sx",
            value=section.sx_in3,
            unit="in^3",
            source=section.source,
            confidence=section.confidence,
        ),
        SourceValue(
            name="Ix",
            value=section.ix_in4,
            unit="in^4",
            source=section.source,
            confidence=section.confidence,
        ),
    ]


def reference_source_values(entry: DesignValueEntry) -> list[SourceValue]:
    """Return traceable sawn-lumber reference design values."""

    return [
        SourceValue(
            name="Fb",
            value=entry.values.fb_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="Ft",
            value=entry.values.ft_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="Fv",
            value=entry.values.fv_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="Fc_perp",
            value=entry.values.fc_perp_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="Fc",
            value=entry.values.fc_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="E",
            value=entry.values.e_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
        SourceValue(
            name="Emin",
            value=entry.values.emin_psi,
            unit="psi",
            source=entry.source,
            confidence=entry.confidence,
        ),
    ]


def governing_check(checks: list[CodeCheck]) -> tuple[str, float, bool]:
    """Return governing check name, max utilization, and overall pass/fail."""

    governing = max(checks, key=lambda check: check.ratio)
    return governing.name, governing.ratio, all(check.passed for check in checks)


def material_spec(
    material_type: str,
    section: SectionEntry,
    species: str | None,
    grade: str | None,
) -> MaterialSpec:
    """Build a trace material specification from catalogue data."""

    return MaterialSpec(
        material_type=material_type,  # type: ignore[arg-type]
        species=species,
        grade=grade,
        nominal_size=section.nominal,
        actual_width_in=section.actual_width_in,
        actual_depth_in=section.actual_depth_in,
    )


def update_trace_governing(trace: CalculationTrace) -> CalculationTrace:
    """Populate governing check fields on a trace."""

    name, ratio, passed = governing_check(trace.checks)
    trace.governing_check = name
    trace.final_utilization = ratio
    if trace.selection_mode == "catalogue_selected" and 0.80 <= ratio < 0.90:
        trace.warning = None
    elif ratio > 0.95:
        trace.warning = "Near-capacity - strongly consider upsizing."
    elif ratio > 0.80:
        trace.warning = "High utilisation - verify adequacy of safety margin."
    else:
        trace.warning = None
    trace.passed = passed
    return trace


def catalogue_member_designation(material: MaterialSpec) -> str:
    """Return a human-readable catalogue member designation for trace notes."""

    parts = [material.nominal_size or ""]
    if material.species:
        parts.append(material.species)
    if material.grade:
        parts.append(material.grade)
    return " ".join(part for part in parts if part)


def annotate_catalogue_selection(
    result: MemberResult,
    ordered_passing: Sequence[MemberResult],
    *,
    auto_upsized: bool,
    auto_upsize_reason: str,
    minimum_passing_member: str,
) -> MemberResult:
    """Attach catalogue-selection metadata and warning behavior to the selected result."""

    trace = result.trace
    trace.selection_mode = "catalogue_selected"
    trace.auto_upsized = auto_upsized
    trace.auto_upsize_reason = auto_upsize_reason
    trace.minimum_passing_member = minimum_passing_member
    selected_index = ordered_passing.index(result)
    if 0.80 <= trace.final_utilization < 0.90:
        if selected_index + 1 < len(ordered_passing):
            next_member = catalogue_member_designation(ordered_passing[selected_index + 1].material)
            trace.catalogue_note = f"Minimum passing size selected. Next size up: {next_member}."
        else:
            trace.catalogue_note = (
                "Minimum passing size selected. No larger catalogue member available."
            )
    else:
        trace.catalogue_note = ""
    update_trace_governing(trace)
    return result


def annotate_user_declared_selection(result: MemberResult) -> MemberResult:
    """Attach user-declared selection metadata and preserve warning behavior."""

    trace = result.trace
    trace.selection_mode = "user_declared"
    trace.catalogue_note = ""
    trace.auto_upsized = False
    trace.auto_upsize_reason = ""
    trace.minimum_passing_member = ""
    update_trace_governing(trace)
    return result
