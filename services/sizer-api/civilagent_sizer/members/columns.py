"""Axial sawn-lumber column sizing."""

from civilagent_sizer.catalogue import get_design_values, get_section, get_timber_design_values
from civilagent_sizer.connectors import select_post_base
from civilagent_sizer.members.common import (
    material_spec,
    nominal_sort_key,
    reference_source_values,
    section_source_values,
    update_trace_governing,
)
from civilagent_sizer.nds.adjustments import sawn_lumber_adjustments
from civilagent_sizer.nds.checks import axial_check
from civilagent_sizer.trace.models import CalculationTrace, LoadTrace, MemberResult, SourceValue

COLUMN_CANDIDATES = ("4x4", "4x6", "6x6", "6x8", "8x8")


def size_column(
    *,
    member_id: str,
    axial_load_lb: float,
    height_ft: float,
    species: str,
    grade: str,
    incised: bool = False,
) -> MemberResult:
    """Size an axially loaded sawn-lumber column per NDS 2018 3.7.1."""

    results: list[MemberResult] = []
    for nominal in COLUMN_CANDIDATES:
        try:
            results.append(
                _evaluate_column(
                    member_id=member_id,
                    nominal=nominal,
                    axial_load_lb=axial_load_lb,
                    height_ft=height_ft,
                    species=species,
                    grade=grade,
                    incised=incised,
                )
            )
        except (KeyError, ValueError):
            continue
    passing = [result for result in results if result.trace.passed]
    if passing:
        selected = min(
            passing,
            key=lambda result: (
                (result.material.actual_width_in or 0) * (result.material.actual_depth_in or 0),
                nominal_sort_key(result.material.nominal_size or "999x999"),
            ),
        )
        selected.selected = True
        return selected
    if not results:
        raise ValueError("No column candidates could be evaluated")
    results[-1].selected = False
    return results[-1]


def _evaluate_column(
    *,
    member_id: str,
    nominal: str,
    axial_load_lb: float,
    height_ft: float,
    species: str,
    grade: str,
    incised: bool,
) -> MemberResult:
    section = get_section(nominal, material_type="sawn_lumber")
    if section.family == "timber":
        reference = get_timber_design_values(species, grade, "posts_and_timbers")
        apply_cf = False
    else:
        reference = get_design_values(species, grade, nominal)
        apply_cf = True
    adjustments = sawn_lumber_adjustments(
        species=species,
        nominal=nominal,
        load_combination="D+L",
        spacing_in=None,
        repetitive=False,
        incised=incised,
        bearing_length_in=section.actual_width_in,
        at_bearing_end=True,
        compression_edge_braced=False,
        fb_ref_psi=reference.values.fb_psi,
        fc_ref_psi=reference.values.fc_psi,
        emin_ref_psi=reference.values.emin_psi,
        width_in=section.actual_width_in,
        depth_in=section.actual_depth_in,
        unbraced_length_in=height_ft * 12.0,
        apply_size_factor=apply_cf,
    )
    fc_prime = reference.values.fc_psi * adjustments.fc
    check = axial_check(axial_load_lb, fc_prime, section.area_in2)
    connections = {}
    if check.passed:
        connections = {
            "base": select_post_base(
                post_nominal=nominal,
                demand_lb=axial_load_lb,
                interface=f"{nominal} wood column to concrete footing post base",
            )
        }
    material = material_spec("sawn_lumber", section, species, grade)
    trace = CalculationTrace(
        member_id=member_id,
        member_type="column",
        material=material,
        span_ft=height_ft,
        length_ft=height_ft,
        loads=[
            LoadTrace(
                name="axial load",
                value=axial_load_lb,
                unit="lb",
                source="Beam reaction from ASD D+L",
                load_type="D+L",
            )
        ],
        section_properties=section_source_values(section),
        reference_design_values=reference_source_values(reference),
        adjusted_design_values=[
            SourceValue(
                name="F'c",
                value=fc_prime,
                unit="psi",
                source="NDS 2018 3.7.1 and adjustment product",
            )
        ],
        adjustment_factors=[
            item for item in adjustments.traces if set(item.applies_to) & {"Fc", "Emin"}
        ],
        checks=[check],
        connections=connections,
        assumptions=[
            "Column is axially loaded only; no beam-column interaction.",
            "Pinned-pinned effective length factor Ke = 1.0.",
        ],
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type="column",
        selected=trace.passed,
        material=material,
        span_ft=height_ft,
        length_ft=height_ft,
        trace=trace,
    )
