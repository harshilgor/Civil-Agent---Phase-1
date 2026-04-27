"""Beam sizing for simply supported sawn-lumber and glulam members."""

from civilagent_sizer.catalogue import (
    get_design_values,
    get_glulam_design_values,
    get_lvl_design_values,
    get_section,
    get_timber_design_values,
    list_sections,
)
from civilagent_sizer.catalogue.loader import load_yaml, select_catalogue_result
from civilagent_sizer.members.common import (
    annotate_catalogue_selection,
    annotate_user_declared_selection,
    catalogue_member_designation,
    material_spec,
    nominal_sort_key,
    reference_source_values,
    section_source_values,
    update_trace_governing,
)
from civilagent_sizer.nds.adjustments import (
    beam_stability_factor,
    bearing_area_factor,
    glulam_volume_factor,
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
from civilagent_sizer.trace.models import (
    AdjustmentFactorTrace,
    CalculationTrace,
    LoadTrace,
    MemberResult,
    SourceValue,
)

SAWN_BEAM_CANDIDATES = ("4x6", "4x8", "4x10", "4x12", "6x8", "6x10", "6x12", "8x8", "8x10", "8x12")


def size_beam(
    *,
    member_id: str,
    span_ft: float,
    total_length_ft: float,
    dead_load_psf: float,
    live_load_psf: float,
    tributary_width_ft: float,
    species: str,
    grade: str,
    live_limit_ratio: int,
    total_limit_ratio: int,
    material_preference: str = "any",
    incised: bool = False,
    span_config: str = "simple",
    declared_nominal: str | None = None,
    max_utilisation_threshold: float = 0.90,
) -> MemberResult:
    """Size a floor beam per NDS 2018 3.3, 3.4, 3.5, and 3.10."""

    results: list[MemberResult] = []
    if material_preference in {"any", "sawn"}:
        for nominal in SAWN_BEAM_CANDIDATES:
            if declared_nominal is not None and nominal != declared_nominal:
                continue
            try:
                results.append(
                    _evaluate_sawn_beam(
                        member_id=member_id,
                        nominal=nominal,
                        span_ft=span_ft,
                        total_length_ft=total_length_ft,
                        dead_load_psf=dead_load_psf,
                        live_load_psf=live_load_psf,
                        tributary_width_ft=tributary_width_ft,
                        species=species,
                        grade=grade,
                        live_limit_ratio=live_limit_ratio,
                        total_limit_ratio=total_limit_ratio,
                        incised=incised,
                        span_config=span_config,
                    )
                )
            except KeyError:
                continue
    if material_preference in {"any", "glulam"}:
        for section in sorted(
            list_sections(material_type="glulam"),
            key=lambda item: (item.area_in2, item.actual_depth_in),
        ):
            if declared_nominal is not None and section.nominal != declared_nominal:
                continue
            results.append(
                _evaluate_glulam_beam(
                    member_id=member_id,
                    nominal=section.nominal,
                    span_ft=span_ft,
                    total_length_ft=total_length_ft,
                    dead_load_psf=dead_load_psf,
                    live_load_psf=live_load_psf,
                    tributary_width_ft=tributary_width_ft,
                    live_limit_ratio=live_limit_ratio,
                    total_limit_ratio=total_limit_ratio,
                    span_config=span_config,
                )
            )
    if material_preference in {"any", "lvl_1.9E", "lvl_2.0E"}:
        grades = (
            ("lvl_1.9E", "lvl_2.0E") if material_preference == "any" else (material_preference,)
        )
        for grade_name in grades:
            for section in sorted(
                list_sections(material_type="lvl"),
                key=lambda item: (item.area_in2, item.actual_depth_in),
            ):
                if declared_nominal is not None and section.nominal != declared_nominal:
                    continue
                results.append(
                    _evaluate_lvl_beam(
                        member_id=member_id,
                        nominal=section.nominal,
                        grade_name=grade_name,
                        span_ft=span_ft,
                        total_length_ft=total_length_ft,
                        dead_load_psf=dead_load_psf,
                        live_load_psf=live_load_psf,
                        tributary_width_ft=tributary_width_ft,
                        live_limit_ratio=live_limit_ratio,
                        total_limit_ratio=total_limit_ratio,
                        span_config=span_config,
                    )
                )
    if declared_nominal is not None:
        if not results:
            raise ValueError(f"No beam candidate could be evaluated for {declared_nominal}")
        result = results[0]
        result.selected = result.trace.passed
        return annotate_user_declared_selection(result)
    passing = [result for result in results if result.trace.passed]
    if passing:
        ordered = sorted(passing, key=_cost_score if material_preference == "any" else _area_score)
        selection = select_catalogue_result(
            ordered,
            utilization_getter=lambda result: result.trace.final_utilization,
            designation_getter=lambda result: catalogue_member_designation(result.material),
            max_utilisation_threshold=max_utilisation_threshold,
        )
        selected = selection.selected
        selected.selected = True
        annotate_catalogue_selection(
            selected,
            ordered,
            auto_upsized=selection.auto_upsized,
            auto_upsize_reason=selection.auto_upsize_reason,
            minimum_passing_member=selection.minimum_passing_member,
        )
        if material_preference == "any":
            selected.trace.assumptions.append(_cost_assumption(selected))
        return selected
    if not results:
        raise ValueError("No beam candidates could be evaluated")
    fallback = results[-1]
    fallback.selected = False
    return fallback


def _beam_loads(
    dead_load_psf: float, live_load_psf: float, tributary_width_ft: float
) -> tuple[float, float, float]:
    dead_plf = dead_load_psf * tributary_width_ft
    live_plf = live_load_psf * tributary_width_ft
    return dead_plf, live_plf, dead_plf + live_plf


def _area_score(result: MemberResult) -> tuple[float, tuple[float, float]]:
    area = (result.material.actual_width_in or 0.0) * (result.material.actual_depth_in or 0.0)
    return area, nominal_sort_key(result.material.nominal_size or "999x999")


def _cost_score(result: MemberResult) -> tuple[float, float, tuple[float, float]]:
    area = (result.material.actual_width_in or 0.0) * (result.material.actual_depth_in or 0.0)
    length = result.length_ft or result.span_ft or 0.0
    multiplier = _material_cost_multiplier(result)
    return (
        area * length * multiplier,
        area,
        nominal_sort_key(result.material.nominal_size or "999x999"),
    )


def _material_cost_multiplier(result: MemberResult) -> float:
    table = load_yaml("cost/material_multipliers.yaml")["material_cost_multipliers"]["rows"]
    for row in table:
        if row["material_type"] != result.material.material_type:
            continue
        if row["grade"] is None or row["grade"] == result.material.grade:
            return float(row["multiplier"])
    return 1.0


def _cost_assumption(result: MemberResult) -> str:
    table = load_yaml("cost/material_multipliers.yaml")["material_cost_multipliers"]
    multiplier = _material_cost_multiplier(result)
    return (
        f"Material selected by approximate installed cost multiplier {multiplier}; "
        f"source: {table['source']}."
    )


def _evaluate_sawn_beam(
    *,
    member_id: str,
    nominal: str,
    span_ft: float,
    total_length_ft: float,
    dead_load_psf: float,
    live_load_psf: float,
    tributary_width_ft: float,
    species: str,
    grade: str,
    live_limit_ratio: int,
    total_limit_ratio: int,
    incised: bool,
    span_config: str,
) -> MemberResult:
    section = get_section(nominal, material_type="sawn_lumber")
    if section.family == "timber":
        category = (
            "beams_and_stringers"
            if section.actual_depth_in - section.actual_width_in > 2.0
            else "posts_and_timbers"
        )
        reference = get_timber_design_values(species, grade, category)
        apply_cf = False
    else:
        reference = get_design_values(species, grade, nominal)
        apply_cf = True
    dead_plf, live_plf, total_plf = _beam_loads(dead_load_psf, live_load_psf, tributary_width_ft)
    adjustments = sawn_lumber_adjustments(
        species=species,
        nominal=nominal,
        load_combination="D+L",
        spacing_in=None,
        repetitive=False,
        incised=incised,
        bearing_length_in=3.5,
        at_bearing_end=True,
        compression_edge_braced=True,
        fb_ref_psi=reference.values.fb_psi,
        fc_ref_psi=reference.values.fc_psi,
        emin_ref_psi=reference.values.emin_psi,
        width_in=section.actual_width_in,
        depth_in=section.actual_depth_in,
        unbraced_length_in=span_ft * 12.0,
        apply_size_factor=apply_cf,
    )
    return _make_beam_result(
        member_id=member_id,
        member_type="beam",
        material=material_spec("sawn_lumber", section, species, grade),
        section=section,
        reference_values=reference_source_values(reference),
        adjusted_values=[
            SourceValue(
                name="F'b",
                value=reference.values.fb_psi * adjustments.fb,
                unit="psi",
                source="NDS 2018 adjustment product",
            ),
            SourceValue(
                name="F'v",
                value=reference.values.fv_psi * adjustments.fv,
                unit="psi",
                source="NDS 2018 adjustment product",
            ),
            SourceValue(
                name="F'c_perp",
                value=reference.values.fc_perp_psi * adjustments.fc_perp,
                unit="psi",
                source="NDS 2018 adjustment product",
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
        span_ft=span_ft,
        total_length_ft=total_length_ft,
        tributary_width_ft=tributary_width_ft,
        dead_load_psf=dead_load_psf,
        live_load_psf=live_load_psf,
        dead_plf=dead_plf,
        live_plf=live_plf,
        total_plf=total_plf,
        live_limit_ratio=live_limit_ratio,
        total_limit_ratio=total_limit_ratio,
        span_config=span_config,
    )


def _evaluate_glulam_beam(
    *,
    member_id: str,
    nominal: str,
    span_ft: float,
    total_length_ft: float,
    dead_load_psf: float,
    live_load_psf: float,
    tributary_width_ft: float,
    live_limit_ratio: int,
    total_limit_ratio: int,
    span_config: str,
) -> MemberResult:
    section = get_section(nominal, material_type="glulam")
    reference = get_glulam_design_values()
    values = reference.values
    dead_plf, live_plf, total_plf = _beam_loads(dead_load_psf, live_load_psf, tributary_width_ft)
    cd = load_duration_factor("D+L")
    cm = wet_service_factor()
    ct = temperature_factor()
    cb = bearing_area_factor(3.5, at_member_end=True)
    cfu = AdjustmentFactorTrace(
        symbol="Cfu",
        name="Flat use factor",
        value=1.0,
        applies_to=["Fb"],
        source="NDS 2018 5.3.6; edgewise glulam project assumption",
        confidence="high",
        note="Standard edgewise glulam beam.",
    )
    cc = AdjustmentFactorTrace(
        symbol="Cc",
        name="Curvature factor",
        value=1.0,
        applies_to=["Fb"],
        source="NDS 2018 5.3.8; straight-member project assumption",
        confidence="high",
        note="Straight glulam member.",
    )
    cv = glulam_volume_factor(span_ft, section.actual_depth_in, section.actual_width_in)
    fb_reference = values.fbx_negative_psi if span_config != "simple" else values.fbx_positive_psi
    cl = beam_stability_factor(
        fb_star_psi=fb_reference * cd.value * cm.value * ct.value,
        emin_prime_psi=values.ex_min_psi * cm.value * ct.value,
        actual_width_in=section.actual_width_in,
        actual_depth_in=section.actual_depth_in,
        unbraced_length_in=span_ft * 12.0,
        compression_edge_braced=True,
    )
    cl_cv = min(cl.value, cv.value)
    fb_prime = fb_reference * cd.value * cm.value * ct.value * cl_cv * cfu.value * cc.value
    fv_prime = values.fvx_psi * cd.value * cm.value * ct.value
    fc_perp_prime = values.fc_perp_x_psi * cm.value * ct.value * cb.value
    e_prime = values.ex_psi * cm.value * ct.value
    reference_values = [
        SourceValue(
            name="Fbx_positive",
            value=values.fbx_positive_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
        SourceValue(
            name="Fbx_negative",
            value=values.fbx_negative_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
        SourceValue(
            name="Fvx",
            value=values.fvx_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
        SourceValue(
            name="Fc_perp_x",
            value=values.fc_perp_x_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
        SourceValue(
            name="Ex",
            value=values.ex_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
        SourceValue(
            name="Ex_min",
            value=values.ex_min_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
    ]
    adjusted_values = [
        SourceValue(
            name="min(CL,CV)",
            value=cl_cv,
            source="NDS 2018 5.3 adjustment rule from supplied research PDF page 6",
        ),
        SourceValue(
            name="F'b", value=fb_prime, unit="psi", source="NDS 2018 glulam adjustment product"
        ),
        SourceValue(
            name="F'v", value=fv_prime, unit="psi", source="NDS 2018 glulam adjustment product"
        ),
        SourceValue(
            name="F'c_perp",
            value=fc_perp_prime,
            unit="psi",
            source="NDS 2018 glulam adjustment product",
        ),
        SourceValue(name="E'", value=e_prime, unit="psi", source="NDS 2018 3.5 adjusted modulus"),
    ]
    return _make_beam_result(
        member_id=member_id,
        member_type="beam",
        material=material_spec("glulam", section, "Douglas Fir", reference.grade),
        section=section,
        reference_values=reference_values,
        adjusted_values=adjusted_values,
        adjustment_factors=[cd, cm, ct, cl, cv, cfu, cc, cb],
        fb_prime=fb_prime,
        fv_prime=fv_prime,
        fc_perp_prime=fc_perp_prime,
        e_prime=e_prime,
        span_ft=span_ft,
        total_length_ft=total_length_ft,
        tributary_width_ft=tributary_width_ft,
        dead_load_psf=dead_load_psf,
        live_load_psf=live_load_psf,
        dead_plf=dead_plf,
        live_plf=live_plf,
        total_plf=total_plf,
        live_limit_ratio=live_limit_ratio,
        total_limit_ratio=total_limit_ratio,
        span_config=span_config,
    )


def _evaluate_lvl_beam(
    *,
    member_id: str,
    nominal: str,
    grade_name: str,
    span_ft: float,
    total_length_ft: float,
    dead_load_psf: float,
    live_load_psf: float,
    tributary_width_ft: float,
    live_limit_ratio: int,
    total_limit_ratio: int,
    span_config: str,
) -> MemberResult:
    section = get_section(nominal, material_type="lvl")
    reference = get_lvl_design_values(grade_name)
    values = reference.values
    dead_plf, live_plf, total_plf = _beam_loads(dead_load_psf, live_load_psf, tributary_width_ft)
    cd = load_duration_factor("D+L")
    cm = wet_service_factor()
    ct = temperature_factor()
    cb = bearing_area_factor(3.5, at_member_end=True)
    ci = AdjustmentFactorTrace(
        symbol="Ci",
        name="Incising factor",
        value=1.0,
        applies_to=["Fb", "Fv", "Fc_perp", "Fc", "E", "Emin"],
        source="NDS 2018 Chapter 8 / Weyerhaeuser TJ-9000; non-incised LVL project assumption",
        confidence="requires_verification",
        note="LVL is treated as non-incised interior product.",
    )
    cv = lvl_volume_factor(span_ft, section.actual_depth_in, section.actual_width_in)
    cr = lvl_repetitive_member_factor(section.actual_width_in)
    c_ft_length = lvl_tension_length_factor(total_length_ft)
    cl = beam_stability_factor(
        fb_star_psi=values.fb_psi * cd.value * cm.value * ct.value * cr.value * ci.value,
        emin_prime_psi=values.emin_psi * cm.value * ct.value * ci.value,
        actual_width_in=section.actual_width_in,
        actual_depth_in=section.actual_depth_in,
        unbraced_length_in=span_ft * 12.0,
        compression_edge_braced=True,
    )
    cl_cv = min(cl.value, cv.value)
    fb_prime = values.fb_psi * cd.value * cm.value * ct.value * cl_cv * cr.value * ci.value
    fv_prime = values.fv_psi * cd.value * cm.value * ct.value * ci.value
    fc_perp_prime = values.fc_perp_psi * cm.value * ct.value * ci.value * cb.value
    e_prime = values.e_psi * cm.value * ct.value * ci.value
    ft_prime = values.ft_psi * cd.value * cm.value * ct.value * c_ft_length.value * ci.value
    reference_values = [
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
            name="Fc",
            value=values.fc_psi,
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
        SourceValue(
            name="Emin",
            value=values.emin_psi,
            unit="psi",
            source=reference.source,
            confidence=reference.confidence,
        ),
    ]
    adjusted_values = [
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
    ]
    result = _make_beam_result(
        member_id=member_id,
        member_type="beam",
        material=material_spec("lvl", section, "Trus Joist Microllam LVL", reference.grade),
        section=section,
        reference_values=reference_values,
        adjusted_values=adjusted_values,
        adjustment_factors=[cd, cm, ct, cl, cv, cr, c_ft_length, ci, cb],
        fb_prime=fb_prime,
        fv_prime=fv_prime,
        fc_perp_prime=fc_perp_prime,
        e_prime=e_prime,
        span_ft=span_ft,
        total_length_ft=total_length_ft,
        tributary_width_ft=tributary_width_ft,
        dead_load_psf=dead_load_psf,
        live_load_psf=live_load_psf,
        dead_plf=dead_plf,
        live_plf=live_plf,
        total_plf=total_plf,
        live_limit_ratio=live_limit_ratio,
        total_limit_ratio=total_limit_ratio,
        span_config=span_config,
    )
    result.trace.assumptions.append(
        
            "LVL reference design values from manufacturer publication. "
            "Independent verification against Weyerhaeuser iLevel TJ-9000 "
            "required before stamping."
        
    )
    return result


def _make_beam_result(
    *,
    member_id: str,
    member_type: str,
    material,
    section,
    reference_values,
    adjusted_values,
    adjustment_factors,
    fb_prime: float,
    fv_prime: float,
    fc_perp_prime: float,
    e_prime: float,
    span_ft: float,
    total_length_ft: float,
    tributary_width_ft: float,
    dead_load_psf: float,
    live_load_psf: float,
    dead_plf: float,
    live_plf: float,
    total_plf: float,
    live_limit_ratio: int,
    total_limit_ratio: int,
    span_config: str,
) -> MemberResult:
    demand = uniform_beam_demand(
        span_config=span_config,
        dead_plf=dead_plf,
        live_plf=live_plf,
        span_ft=span_ft,
        e_psi=e_prime,
        ix_in4=section.ix_in4,
    )
    bearing_area = 3.5 * section.actual_width_in
    max_reaction = max((*demand.end_reactions_lb, *demand.interior_reactions_lb))
    checks = [
        bending_check(demand.moment_inlb, fb_prime, section.sx_in3),
        shear_check(demand.shear_lb, fv_prime, section.area_in2),
        deflection_check(demand.live_deflection_in, span_ft, live_limit_ratio, "live"),
        deflection_check(demand.total_deflection_in, span_ft, total_limit_ratio, "total"),
        bearing_check(max_reaction, fc_perp_prime, bearing_area),
    ]
    checks[0].details.update(
        {
            "span_config": span_config,
            "positive_moment_inlb": demand.positive_moment_inlb,
            "negative_moment_inlb": demand.negative_moment_inlb,
            "design_moment_type": demand.design_moment_type,
            "demand_source": demand.source,
        }
    )
    checks[1].details.update({"span_config": span_config, "demand_source": demand.source})
    deflection_details = _deflection_trace_details(span_config)
    checks[2].details.update(deflection_details)
    checks[3].details.update(deflection_details)
    trace = CalculationTrace(
        member_id=member_id,
        member_type=member_type,
        material=material,
        span_ft=span_ft,
        length_ft=total_length_ft,
        span_config=span_config,
        span_count=demand.span_count,
        interior_support_reactions=list(demand.interior_reactions_lb),
        design_moment_type=demand.design_moment_type,
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
                name="beam tributary width",
                value=tributary_width_ft,
                unit="ft",
                source="Project layout tributary geometry",
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
            LoadTrace(
                name="demand model span count",
                value=demand.span_count,
                unit="spans",
                source=demand.source,
            ),
            *[
                LoadTrace(
                    name=f"end support reaction {index + 1}",
                    value=reaction,
                    unit="lb",
                    source=demand.source,
                    load_type="D+L",
                )
                for index, reaction in enumerate(demand.end_reactions_lb)
            ],
            *[
                LoadTrace(
                    name=f"interior support reaction {index + 1}",
                    value=reaction,
                    unit="lb",
                    source=demand.source,
                    load_type="D+L",
                )
                for index, reaction in enumerate(demand.interior_reactions_lb)
            ],
        ],
        section_properties=section_source_values(section),
        reference_design_values=reference_values,
        adjusted_design_values=adjusted_values,
        adjustment_factors=adjustment_factors,
        checks=checks,
        assumptions=[
            f"Beam demand model: {span_config}; source: {demand.source}.",
            (
                "Compression edge treated as laterally braced by connected floor "
                "framing; CL = 1.0 unless d/b exception governs."
            ),
            (
                "Bearing length at supports assumed 3.5 in and Cb = 1.0 for "
                "conservative end-bearing check."
            ),
        ],
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type=member_type,
        selected=trace.passed,
        material=material,
        span_ft=span_ft,
        length_ft=total_length_ft,
        trace=trace,
    )


def _deflection_trace_details(span_config: str) -> dict[str, str]:
    if span_config == "two_span_equal":
        return {
            "deflection_coefficient": "1/185",
            "deflection_source": (
                "Roark's Formulas for Stress and Strain, 8th edition, Table 8.1, Case 3"
            ),
        }
    if span_config == "three_span_equal":
        return {
            "deflection_coefficient": "1/145",
            "deflection_source": (
                "Roark's Formulas for Stress and Strain, 8th edition, Table 8.1, Case 5"
            ),
        }
    return {
        "deflection_coefficient": "5/384",
        "deflection_source": (
            "Classical beam mechanics; AISC Steel Construction Manual Table 3-23 Case 1"
        ),
    }
