"""Header sizing for residential door and window openings."""

from math import ceil

from civilagent_sizer.catalogue import get_design_values, get_lvl_design_values, get_section
from civilagent_sizer.catalogue.loader import load_yaml, select_catalogue_result
from civilagent_sizer.members.common import (
    annotate_catalogue_selection,
    annotate_user_declared_selection,
    catalogue_member_designation,
    material_spec,
    reference_source_values,
    section_source_values,
    update_trace_governing,
)
from civilagent_sizer.nds.adjustments import (
    AdjustmentFactorTrace,
    beam_stability_factor,
    bearing_area_factor,
    load_duration_factor,
    lvl_repetitive_member_factor,
    lvl_tension_length_factor,
    lvl_volume_factor,
    sawn_lumber_adjustments,
    temperature_factor,
    wet_service_factor,
)
from civilagent_sizer.nds.checks import (
    bearing_check,
    bending_check,
    deflection_check,
    shear_check,
)
from civilagent_sizer.nds.demand import uniform_beam_demand
from civilagent_sizer.schemas import HeaderInput
from civilagent_sizer.trace.models import CalculationTrace, LoadTrace, MemberResult, SourceValue

SAWN_HEADER_CANDIDATES = ("double_2x4", "double_2x6", "double_2x8", "double_2x10", "double_2x12")
LVL_HEADER_CANDIDATES = (
    "1.75x5.5",
    "1.75x7.25",
    "1.75x9.25",
    "1.75x11.25",
    "1.75x14",
    "3.5x9.25",
    "3.5x11.25",
    "3.5x14",
)


def size_header(
    member_id: str,
    header: HeaderInput,
    declared_nominal: str | None = None,
    max_utilisation_threshold: float = 0.90,
) -> MemberResult:
    """Size a simple-span header using NDS beam checks and declared tributary loads."""

    dead_psf, live_psf, load_components, load_note = _header_loads(header.header_load_condition)
    candidates: list[MemberResult] = []
    if header.material_preference in {"any", "sawn"}:
        for nominal in _sawn_header_candidates_for_wall(header.wall_thickness):
            if declared_nominal is not None and nominal != declared_nominal:
                continue
            candidates.append(
                _evaluate_sawn_header(
                    member_id=member_id,
                    nominal=nominal,
                    header=header,
                    dead_psf=dead_psf,
                    live_psf=live_psf,
                    load_components=load_components,
                    load_note=load_note,
                )
                )
    if header.material_preference in {"any", "lvl_1.9E", "lvl_2.0E"}:
        grades = (
            ("lvl_1.9E", "lvl_2.0E")
            if header.material_preference == "any"
            else (header.material_preference,)
        )
        for grade_name in grades:
            for nominal in LVL_HEADER_CANDIDATES:
                if declared_nominal is not None and nominal != declared_nominal:
                    continue
                candidates.append(
                    _evaluate_lvl_header(
                        member_id=member_id,
                        nominal=nominal,
                        grade_name=grade_name,
                        header=header,
                        dead_psf=dead_psf,
                        live_psf=live_psf,
                        load_components=load_components,
                        load_note=load_note,
                    )
                )
    if declared_nominal is not None:
        if not candidates:
            raise ValueError(f"No header candidate could be evaluated for {declared_nominal}")
        result = candidates[0]
        result.selected = result.trace.passed
        return annotate_user_declared_selection(result)
    passing = [result for result in candidates if result.trace.passed]
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
    if not candidates:
        raise ValueError("No header candidates available for input")
    candidates[-1].selected = False
    return candidates[-1]


def _sawn_header_candidates_for_wall(wall_thickness: str) -> tuple[str, ...]:
    max_depth = 9.25 if wall_thickness == "2x4" else 11.25
    return tuple(
        nominal
        for nominal in SAWN_HEADER_CANDIDATES
        if get_section(nominal, "sawn_lumber").actual_depth_in <= max_depth
    )


def _header_loads(condition: str) -> tuple[float, float, list[dict], str]:
    table = load_yaml("limits/header_load_defaults.yaml")["header_load_conditions"]
    row = table[condition]
    dead = sum(float(item["value_psf"]) for item in row["components"] if item["load_type"] == "D")
    live = sum(float(item["value_psf"]) for item in row["components"] if item["load_type"] == "L")
    return dead, live, row["components"], row["notes"]


def _jack_studs_required(header: HeaderInput) -> tuple[int, str | None, str, str]:
    table = load_yaml("prescriptive/jack_studs.yaml")
    source = table["source"]
    confidence = table["confidence"]
    fallback_note = (
        "Jack stud count used conservative fallback ceil(opening_span_ft / 4.0) "
        "because the opening is outside the prescriptive table inputs."
    )

    if (
        header.building_width_ft is None
        or header.ground_snow_load_psf is None
        or header.rough_opening_ft > 12.0
    ):
        return _conservative_jack_studs(header.rough_opening_ft), fallback_note, source, confidence

    table_key = _jack_stud_table_key(header)
    snow_key = _jack_stud_snow_key(header)
    building_key = _jack_stud_limit_key(
        "building_width_le_", header.building_width_ft, (24.0, 28.0, 32.0, 36.0)
    )
    span_limits = (4.0, 6.0, 8.0, 10.0, 12.0)
    if table_key == "two_floors_roof_ceiling":
        span_limits = (4.0, 6.0, 8.0, 10.0)
    span_key = _jack_stud_limit_key("span_le_", header.rough_opening_ft, span_limits)
    if building_key is None or span_key is None:
        return _conservative_jack_studs(header.rough_opening_ft), fallback_note, source, confidence

    value = table["tables"][table_key][snow_key][building_key][span_key]
    return int(value), None, source, confidence


def _conservative_jack_studs(opening_span_ft: float) -> int:
    return max(1, ceil(opening_span_ft / 4.0))


def _jack_stud_table_key(header: HeaderInput) -> str:
    stories_supported = header.stories_supported
    if stories_supported is None:
        stories_supported = {
            "roof_only": "roof_only",
            "one_floor_above": "one_floor",
            "floor_only": "one_floor",
            "two_floors_above": "two_floors",
        }[header.header_load_condition]
    return {
        "roof_only": "roof_ceiling_only",
        "one_floor": "one_floor_roof_ceiling",
        "two_floors": "two_floors_roof_ceiling",
    }[stories_supported]


def _jack_stud_snow_key(header: HeaderInput) -> str:
    if _jack_stud_table_key(header) == "two_floors_roof_ceiling":
        return "any_snow"
    return "snow_le_30psf" if (header.ground_snow_load_psf or 0.0) <= 30.0 else "snow_le_50psf"


def _jack_stud_limit_key(prefix: str, value: float, limits: tuple[float, ...]) -> str | None:
    for limit in limits:
        if value <= limit:
            formatted = str(int(limit)) if limit.is_integer() else str(limit)
            return f"{prefix}{formatted}ft"
    return None


def _evaluate_sawn_header(
    *,
    member_id: str,
    nominal: str,
    header: HeaderInput,
    dead_psf: float,
    live_psf: float,
    load_components: list[dict],
    load_note: str,
) -> MemberResult:
    section = get_section(nominal, "sawn_lumber")
    base_nominal = nominal.replace("double_", "")
    reference = get_design_values(header.species, header.grade, base_nominal)
    dead_plf = dead_psf * header.tributary_width_ft
    live_plf = live_psf * header.tributary_width_ft
    adjustments = sawn_lumber_adjustments(
        species=header.species,
        nominal=base_nominal,
        load_combination="D+L",
        spacing_in=None,
        repetitive=False,
        incised=False,
        bearing_length_in=header.bearing_length_in,
        at_bearing_end=True,
        compression_edge_braced=True,
        fb_ref_psi=reference.values.fb_psi,
        fc_ref_psi=reference.values.fc_psi,
        emin_ref_psi=reference.values.emin_psi,
        width_in=section.actual_width_in,
        depth_in=section.actual_depth_in,
        unbraced_length_in=header.rough_opening_ft * 12.0,
    )
    return _make_header_result(
        member_id=member_id,
        header=header,
        section=section,
        material=material_spec("sawn_lumber", section, header.species, header.grade),
        reference_values=reference_source_values(reference),
        adjusted_values=[
            SourceValue(
                name="F'b",
                value=reference.values.fb_psi * adjustments.fb,
                unit="psi",
                source="NDS 2018 Table 2.3.1 and 4.3 adjustment product",
            ),
            SourceValue(
                name="F'v",
                value=reference.values.fv_psi * adjustments.fv,
                unit="psi",
                source="NDS 2018 Table 2.3.1 and 4.3 adjustment product",
            ),
            SourceValue(
                name="F'c_perp",
                value=reference.values.fc_perp_psi * adjustments.fc_perp,
                unit="psi",
                source="NDS 2018 3.10 and adjustment product",
            ),
            SourceValue(
                name="E'",
                value=reference.values.e_psi * adjustments.e,
                unit="psi",
                source="NDS 2018 3.5 adjusted modulus",
            ),
        ],
        adjustment_factors=[
            item
            for item in adjustments.traces
            if set(item.applies_to) & {"Fb", "Fv", "Fc_perp", "E"}
        ],
        fb_prime=reference.values.fb_psi * adjustments.fb,
        fv_prime=reference.values.fv_psi * adjustments.fv,
        fc_perp_prime=reference.values.fc_perp_psi * adjustments.fc_perp,
        e_prime=reference.values.e_psi * adjustments.e,
        dead_psf=dead_psf,
        live_psf=live_psf,
        dead_plf=dead_plf,
        live_plf=live_plf,
        load_components=load_components,
        load_note=load_note,
    )


def _evaluate_lvl_header(
    *,
    member_id: str,
    nominal: str,
    grade_name: str,
    header: HeaderInput,
    dead_psf: float,
    live_psf: float,
    load_components: list[dict],
    load_note: str,
) -> MemberResult:
    section = get_section(nominal, "lvl")
    reference = get_lvl_design_values(grade_name)
    values = reference.values
    dead_plf = dead_psf * header.tributary_width_ft
    live_plf = live_psf * header.tributary_width_ft
    cd = load_duration_factor("D+L")
    cm = wet_service_factor()
    ct = temperature_factor()
    cb = bearing_area_factor(header.bearing_length_in, at_member_end=True)
    ci = AdjustmentFactorTrace(
        symbol="Ci",
        name="Incising factor",
        value=1.0,
        applies_to=["Fb", "Fv", "Fc_perp", "Fc", "E", "Emin"],
        source="NDS 2018 Chapter 8 / Weyerhaeuser TJ-9000; non-incised LVL header assumption",
        confidence="requires_verification",
        note="LVL is treated as non-incised interior product.",
    )
    cv = lvl_volume_factor(
        header.rough_opening_ft, section.actual_depth_in, section.actual_width_in
    )
    cr = lvl_repetitive_member_factor(section.actual_width_in)
    c_ft_length = lvl_tension_length_factor(header.rough_opening_ft)
    cl = beam_stability_factor(
        fb_star_psi=values.fb_psi * cd.value * cm.value * ct.value * cr.value * ci.value,
        emin_prime_psi=values.emin_psi,
        actual_width_in=section.actual_width_in,
        actual_depth_in=section.actual_depth_in,
        unbraced_length_in=header.rough_opening_ft * 12.0,
        compression_edge_braced=True,
    )
    cl_cv = min(cl.value, cv.value)
    fb_prime = values.fb_psi * cd.value * cm.value * ct.value * cl_cv * cr.value * ci.value
    fv_prime = values.fv_psi * cd.value * cm.value * ct.value * ci.value
    fc_perp_prime = values.fc_perp_psi * cm.value * ct.value * ci.value * cb.value
    e_prime = values.e_psi * cm.value * ct.value * ci.value
    ft_prime = values.ft_psi * cd.value * cm.value * ct.value * c_ft_length.value * ci.value
    return _make_header_result(
        member_id=member_id,
        header=header,
        section=section,
        material=material_spec("lvl", section, "Trus Joist Microllam LVL", reference.grade),
        reference_values=[
            SourceValue(
                name="Fb",
                value=values.fb_psi,
                unit="psi",
                source=reference.source,
                confidence=reference.confidence,
            ),
            SourceValue(
                name="Fv",
                value=values.fv_psi,
                unit="psi",
                source=reference.source,
                confidence=reference.confidence,
            ),
            SourceValue(
                name="Fc_perp",
                value=values.fc_perp_psi,
                unit="psi",
                source=reference.source,
                confidence=reference.confidence,
            ),
            SourceValue(
                name="E",
                value=values.e_psi,
                unit="psi",
                source=reference.source,
                confidence=reference.confidence,
            ),
        ],
        adjusted_values=[
            SourceValue(
                name="min(CL,CV)",
                value=cl_cv,
                source="NDS 2018 Chapter 8 / Weyerhaeuser TJ-9000 LVL adjustment rule",
            ),
            SourceValue(
                name="F't",
                value=ft_prime,
                unit="psi",
                source="Weyerhaeuser Microllam LVL Ft length adjustment product",
            ),
            SourceValue(
                name="F'b",
                value=fb_prime,
                unit="psi",
                source="NDS 2018 Table 8.3.1 and Weyerhaeuser TJ-9000 adjustment product",
            ),
            SourceValue(
                name="F'v",
                value=fv_prime,
                unit="psi",
                source="NDS 2018 Table 8.3.1 and Weyerhaeuser TJ-9000 adjustment product",
            ),
            SourceValue(
                name="F'c_perp",
                value=fc_perp_prime,
                unit="psi",
                source="NDS 2018 Table 8.3.1 and Weyerhaeuser TJ-9000 adjustment product",
            ),
            SourceValue(
                name="E'",
                value=e_prime,
                unit="psi",
                source="NDS 2018 Table 8.3.1 and Weyerhaeuser TJ-9000 adjusted modulus",
            ),
        ],
        adjustment_factors=[cd, cm, ct, cl, cv, cr, c_ft_length, ci, cb],
        fb_prime=fb_prime,
        fv_prime=fv_prime,
        fc_perp_prime=fc_perp_prime,
        e_prime=e_prime,
        dead_psf=dead_psf,
        live_psf=live_psf,
        dead_plf=dead_plf,
        live_plf=live_plf,
        load_components=load_components,
        load_note=load_note,
    )


def _make_header_result(
    *,
    member_id: str,
    header: HeaderInput,
    section,
    material,
    reference_values,
    adjusted_values,
    adjustment_factors,
    fb_prime: float,
    fv_prime: float,
    fc_perp_prime: float,
    e_prime: float,
    dead_psf: float,
    live_psf: float,
    dead_plf: float,
    live_plf: float,
    load_components: list[dict],
    load_note: str,
) -> MemberResult:
    demand = uniform_beam_demand(
        span_config="simple",
        dead_plf=dead_plf,
        live_plf=live_plf,
        span_ft=header.rough_opening_ft,
        e_psi=e_prime,
        ix_in4=section.ix_in4,
    )
    reaction = demand.end_reactions_lb[0]
    bearing_area = header.bearing_length_in * section.actual_width_in
    jack_count, jack_warning, jack_source, jack_confidence = _jack_studs_required(header)
    checks = [
        bending_check(demand.moment_inlb, fb_prime, section.sx_in3),
        shear_check(demand.shear_lb, fv_prime, section.area_in2),
        deflection_check(demand.live_deflection_in, header.rough_opening_ft, 360, "live"),
        deflection_check(demand.total_deflection_in, header.rough_opening_ft, 240, "total"),
        bearing_check(reaction, fc_perp_prime, bearing_area),
    ]
    loads = [
        LoadTrace(
            name=item["name"],
            value=float(item["value_psf"]),
            unit="psf",
            source=item["source"],
            load_type=item["load_type"],
        )
        for item in load_components
    ]
    loads.extend(
        [
            LoadTrace(
                name="header tributary width",
                value=header.tributary_width_ft,
                unit="ft",
                source="Header input; required explicit project geometry",
            ),
            LoadTrace(
                name="dead line load",
                value=dead_plf,
                unit="plf",
                source="sum dead psf * tributary width",
                load_type="D",
            ),
            LoadTrace(
                name="live line load",
                value=live_plf,
                unit="plf",
                source="sum live psf * tributary width",
                load_type="L",
            ),
            LoadTrace(
                name="end reaction",
                value=reaction,
                unit="lb",
                source=demand.source,
                load_type="D+L",
            ),
        ]
    )
    assumptions = [
        load_note,
        "Header modeled as a simply supported beam between jack studs.",
        (
            "Default header live deflection L/360 and total deflection L/240 per "
            "IBC 2021 Table 1604.3."
        ),
        "Engineer must verify header tributary width and project-specific loads.",
    ]
    if header.header_load_condition != "roof_only":
        assumptions.append(
            
                "Simplified jack stud table should be verified for multi-storey "
                "or heavily loaded headers."
            
        )
    if jack_warning:
        assumptions.append(jack_warning)
    trace = CalculationTrace(
        member_id=member_id,
        member_type="header",
        material=material,
        span_ft=header.rough_opening_ft,
        length_ft=header.rough_opening_ft,
        span_config="simple",
        span_count=1,
        design_moment_type="positive",
        header_load_condition=header.header_load_condition,
        rough_opening_ft=header.rough_opening_ft,
        wall_thickness=header.wall_thickness,
        tributary_width_ft=header.tributary_width_ft,
        jack_studs_required=jack_count,
        bearing_length_in=header.bearing_length_in,
        loads=loads,
        section_properties=[
            *section_source_values(section),
            SourceValue(
                name="jack_studs_required",
                value=jack_count,
                source=jack_source,
                confidence=jack_confidence,
            ),
        ],
        reference_design_values=reference_values,
        adjusted_design_values=adjusted_values,
        adjustment_factors=adjustment_factors,
        checks=checks,
        assumptions=assumptions,
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type="header",
        selected=trace.passed,
        material=material,
        span_ft=header.rough_opening_ft,
        length_ft=header.rough_opening_ft,
        trace=trace,
    )
