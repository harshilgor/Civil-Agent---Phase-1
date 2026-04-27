"""Floor joist sizing for simply supported sawn-lumber members."""

from civilagent_sizer.catalogue import get_design_values, get_section
from civilagent_sizer.catalogue.loader import select_catalogue_result
from civilagent_sizer.connectors import select_joist_hanger
from civilagent_sizer.members.common import (
    annotate_catalogue_selection,
    annotate_user_declared_selection,
    catalogue_member_designation,
    material_spec,
    reference_source_values,
    section_source_values,
    update_trace_governing,
)
from civilagent_sizer.nds.adjustments import sawn_lumber_adjustments
from civilagent_sizer.nds.checks import (
    bearing_check,
    bending_check,
    deflection_check,
    shear_check,
    simple_uniform_deflection,
    simple_uniform_moment,
    simple_uniform_shear,
)
from civilagent_sizer.trace.models import CalculationTrace, LoadTrace, MemberResult, SourceValue

JOIST_CANDIDATES = ("2x4", "2x6", "2x8", "2x10", "2x12")


def size_joist(
    *,
    member_id: str,
    span_ft: float,
    spacing_in: float,
    dead_load_psf: float,
    live_load_psf: float,
    species: str,
    grade: str,
    live_limit_ratio: int,
    total_limit_ratio: int,
    incised: bool = False,
    minimum_nominal: str | None = None,
    declared_nominal: str | None = None,
    max_utilisation_threshold: float = 0.90,
) -> MemberResult:
    """Size floor joists per NDS 2018 3.3, 3.4, 3.5, 3.10 and 4.3."""

    if declared_nominal is not None:
        candidate_nominals = [declared_nominal]
    else:
        start = (
            JOIST_CANDIDATES.index(minimum_nominal)
            if minimum_nominal in JOIST_CANDIDATES
            else 0
        )
        candidate_nominals = list(JOIST_CANDIDATES[start:])
    evaluated = [
        _evaluate_joist(
            member_id=member_id,
            nominal=nominal,
            span_ft=span_ft,
            spacing_in=spacing_in,
            dead_load_psf=dead_load_psf,
            live_load_psf=live_load_psf,
            species=species,
            grade=grade,
            live_limit_ratio=live_limit_ratio,
            total_limit_ratio=total_limit_ratio,
            incised=incised,
        )
        for nominal in candidate_nominals
    ]
    if declared_nominal is not None:
        if not evaluated:
            raise ValueError(f"No joist candidate could be evaluated for {declared_nominal}")
        result = evaluated[0]
        result.selected = result.trace.passed
        return annotate_user_declared_selection(result)
    passing = [result for result in evaluated if result.trace.passed]
    if passing:
        selection = select_catalogue_result(
            passing,
            utilization_getter=lambda result: result.trace.final_utilization,
            designation_getter=lambda result: catalogue_member_designation(result.material),
            max_utilisation_threshold=max_utilisation_threshold,
        )
        selection.selected.selected = True
        return annotate_catalogue_selection(
            selection.selected,
            passing,
            auto_upsized=selection.auto_upsized,
            auto_upsize_reason=selection.auto_upsize_reason,
            minimum_passing_member=selection.minimum_passing_member,
        )
    evaluated[-1].selected = False
    return evaluated[-1]


def _evaluate_joist(
    *,
    member_id: str,
    nominal: str,
    span_ft: float,
    spacing_in: float,
    dead_load_psf: float,
    live_load_psf: float,
    species: str,
    grade: str,
    live_limit_ratio: int,
    total_limit_ratio: int,
    incised: bool,
) -> MemberResult:
    section = get_section(nominal, material_type="sawn_lumber")
    reference = get_design_values(species, grade, nominal)
    tributary_width_ft = spacing_in / 12.0
    dead_plf = dead_load_psf * tributary_width_ft
    live_plf = live_load_psf * tributary_width_ft
    total_plf = dead_plf + live_plf
    adjustments = sawn_lumber_adjustments(
        species=species,
        nominal=nominal,
        load_combination="D+L",
        spacing_in=spacing_in,
        repetitive=True,
        incised=incised,
        bearing_length_in=1.5,
        at_bearing_end=True,
        compression_edge_braced=True,
        fb_ref_psi=reference.values.fb_psi,
        fc_ref_psi=reference.values.fc_psi,
        emin_ref_psi=reference.values.emin_psi,
        width_in=section.actual_width_in,
        depth_in=section.actual_depth_in,
        unbraced_length_in=span_ft * 12.0,
    )
    fb_prime = reference.values.fb_psi * adjustments.fb
    fv_prime = reference.values.fv_psi * adjustments.fv
    fc_perp_prime = reference.values.fc_perp_psi * adjustments.fc_perp
    e_prime = reference.values.e_psi * adjustments.e
    moment = simple_uniform_moment(total_plf, span_ft)
    shear = simple_uniform_shear(total_plf, span_ft)
    reaction = shear
    bearing_area = 1.5 * section.actual_width_in
    live_deflection = simple_uniform_deflection(live_plf, span_ft, e_prime, section.ix_in4)
    total_deflection = simple_uniform_deflection(total_plf, span_ft, e_prime, section.ix_in4)
    checks = [
        bending_check(moment, fb_prime, section.sx_in3),
        shear_check(shear, fv_prime, section.area_in2),
        deflection_check(live_deflection, span_ft, live_limit_ratio, "live"),
        deflection_check(total_deflection, span_ft, total_limit_ratio, "total"),
        bearing_check(reaction, fc_perp_prime, bearing_area),
    ]
    connections = {}
    if all(check.passed for check in checks):
        connections = {
            "end_a": select_joist_hanger(
                joist_nominal=nominal,
                demand_lb=reaction,
                interface=f"{nominal} {species} joist to supporting member, face mount",
            ),
            "end_b": select_joist_hanger(
                joist_nominal=nominal,
                demand_lb=reaction,
                interface=f"{nominal} {species} joist to supporting member, face mount",
            ),
        }
    material = material_spec("sawn_lumber", section, species, grade)
    trace = CalculationTrace(
        member_id=member_id,
        member_type="joist",
        material=material,
        span_ft=span_ft,
        length_ft=span_ft,
        spacing_in=spacing_in,
        loads=[
            LoadTrace(
                name="dead area load",
                value=dead_load_psf,
                unit="psf",
                source="Project input",
                load_type="D",
            ),
            LoadTrace(
                name="live area load",
                value=live_load_psf,
                unit="psf",
                source="ASCE 7-22 Table 4.3-1 / project input",
                load_type="L",
            ),
            LoadTrace(
                name="tributary width",
                value=tributary_width_ft,
                unit="ft",
                source="Project geometry: joist spacing / 12",
            ),
            LoadTrace(
                name="dead line load",
                value=dead_plf,
                unit="plf",
                source="dead psf * tributary width",
                load_type="D",
            ),
            LoadTrace(
                name="live line load",
                value=live_plf,
                unit="plf",
                source="live psf * tributary width",
                load_type="L",
            ),
            LoadTrace(
                name="total line load",
                value=total_plf,
                unit="plf",
                source="ASD D+L",
                load_type="D+L",
            ),
        ],
        section_properties=section_source_values(section),
        reference_design_values=reference_source_values(reference),
        adjusted_design_values=[
            SourceValue(
                name="F'b",
                value=fb_prime,
                unit="psi",
                source="NDS 2018 Table 2.3.1 and 4.3 adjustment product",
            ),
            SourceValue(
                name="F'v",
                value=fv_prime,
                unit="psi",
                source="NDS 2018 Table 2.3.1 and 4.3 adjustment product",
            ),
            SourceValue(
                name="F'c_perp",
                value=fc_perp_prime,
                unit="psi",
                source="NDS 2018 3.10 and adjustment product",
            ),
            SourceValue(
                name="E'", value=e_prime, unit="psi", source="NDS 2018 3.5 adjusted modulus"
            ),
        ],
        adjustment_factors=[
            item
            for item in adjustments.traces
            if set(item.applies_to) & {"Fb", "Fv", "Fc_perp", "E"}
        ],
        checks=checks,
        connections=connections,
        assumptions=[
            "Simply supported joist with uniform load.",
            "Compression edge continuously braced by floor sheathing; CL = 1.0.",
            "Bearing factor Cb = 1.0 for conservative end-bearing check.",
        ],
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type="joist",
        selected=trace.passed,
        material=material,
        span_ft=span_ft,
        length_ft=span_ft,
        spacing_in=spacing_in,
        trace=trace,
    )
