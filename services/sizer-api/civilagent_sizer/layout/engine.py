"""End-to-end sizing orchestration for rectangular sample layouts."""

from civilagent_sizer.loads import (
    joist_count,
    support_line_load_from_joists,
)
from civilagent_sizer.members import (
    size_beam,
    size_column,
    size_joist,
    size_spread_footing,
    size_strip_footing,
)
from civilagent_sizer.schemas import PlanInput
from civilagent_sizer.trace.models import (
    AssumptionRecord,
    DesignResult,
    MemberResult,
    QuantitySummary,
)


def size_plan_layout(plan: PlanInput, layout_name: str) -> DesignResult:
    """Size one named layout from a structured rectangular floor plan."""

    layout = plan.layout_by_name(layout_name)
    loads = plan.load_parameters
    members: list[MemberResult] = []
    assumptions = _common_assumptions()
    questions = [
        (
            "Official NDS 2018/Supplement verification is still required for "
            "medium-confidence catalogue values."
        ),
        (
            "No wall, roof, snow, wind, seismic, notching, vibration, or connection "
            "loads are included."
        ),
    ]

    joist = size_joist(
        member_id=f"J-{layout.name}-01",
        span_ft=layout.joist_span_ft,
        spacing_in=layout.joist_spacing_in,
        dead_load_psf=loads.dead_load_psf,
        live_load_psf=loads.live_load_psf,
        species=loads.species,
        grade=loads.grade,
        live_limit_ratio=loads.deflection_live_limit,
        total_limit_ratio=loads.deflection_total_limit,
        incised=loads.incised,
        minimum_nominal=loads.minimum_joist_nominal,
    )
    joist.quantity = joist_count(plan.dimensions.length_ft, layout.joist_spacing_in)
    members.append(joist)
    total_area_load = loads.dead_load_psf + loads.live_load_psf

    if layout.layout_type == "perimeter_support":
        short_wall_line_load = support_line_load_from_joists(
            joist_count_value=joist.quantity,
            area_load_psf=total_area_load,
            spacing_in=layout.joist_spacing_in,
            joist_span_ft=layout.joist_span_ft,
            support_length_ft=plan.dimensions.width_ft,
        )
        members.extend(
            [
                size_strip_footing(
                    member_id="F-A-LONG-1",
                    line_load_plf=0.0,
                    length_ft=plan.dimensions.length_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-A-LONG-2",
                    line_load_plf=0.0,
                    length_ft=plan.dimensions.length_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-A-SHORT-1",
                    line_load_plf=short_wall_line_load,
                    length_ft=plan.dimensions.width_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-A-SHORT-2",
                    line_load_plf=short_wall_line_load,
                    length_ft=plan.dimensions.width_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
            ]
        )
        assumptions.append(
            AssumptionRecord(
                description=(
                    "Layout A joist end reactions are accumulated onto both "
                    "short-side bearing wall footings."
                ),
                source="Joist reaction load propagation",
            )
        )

    if layout.layout_type == "center_beam":
        if (
            layout.beam_span_ft is None
            or layout.beam_total_length_ft is None
            or layout.beam_tributary_width_ft is None
        ):
            raise ValueError(
                "Center-beam layout requires beam_span_ft, beam_total_length_ft, "
                "and beam_tributary_width_ft"
            )
        beam = size_beam(
            member_id=f"B-{layout.name}-01",
            span_ft=layout.beam_span_ft,
            total_length_ft=layout.beam_total_length_ft,
            dead_load_psf=loads.dead_load_psf,
            live_load_psf=loads.live_load_psf,
            tributary_width_ft=layout.beam_tributary_width_ft,
            species=loads.species,
            grade=loads.grade,
            live_limit_ratio=loads.deflection_live_limit,
            total_limit_ratio=loads.deflection_total_limit,
            material_preference=loads.beam_material_preference,
            incised=loads.incised,
            span_config=layout.beam_span_config,
        )
        members.append(beam)
        support_reactions = [
            load.value for load in beam.trace.loads if load.name.startswith("end support reaction")
        ]
        endpoint_reaction = support_reactions[0] if support_reactions else 0.0
        midpoint_reaction = (
            beam.trace.interior_support_reactions[0]
            if beam.trace.interior_support_reactions
            else endpoint_reaction * 2.0
        )
        column = size_column(
            member_id=f"C-{layout.name}-MID",
            axial_load_lb=midpoint_reaction,
            height_ft=loads.column_height_ft,
            species=loads.species,
            grade=loads.grade,
            incised=loads.incised,
        )
        members.append(column)
        members.extend(
            [
                size_spread_footing(
                    member_id="F-B-END-1",
                    load_lb=endpoint_reaction,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_spread_footing(
                    member_id="F-B-MID",
                    load_lb=midpoint_reaction,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_spread_footing(
                    member_id="F-B-END-2",
                    load_lb=endpoint_reaction,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-B-PERIM-LONG-1",
                    line_load_plf=0.0,
                    length_ft=plan.dimensions.length_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-B-PERIM-LONG-2",
                    line_load_plf=0.0,
                    length_ft=plan.dimensions.length_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
                size_strip_footing(
                    member_id="F-B-PERIM-SHORT",
                    line_load_plf=support_line_load_from_joists(
                        joist_count_value=joist.quantity,
                        area_load_psf=total_area_load,
                        spacing_in=layout.joist_spacing_in,
                        joist_span_ft=layout.joist_span_ft,
                        support_length_ft=plan.dimensions.width_ft,
                    ),
                    length_ft=plan.dimensions.width_ft,
                    allowable_soil_psf=loads.soil_bearing_psf,
                ),
            ]
        )
        assumptions.append(
            AssumptionRecord(
                description=_center_beam_assumption(layout.beam_span_config, layout.beam_span_ft),
                source="Project layout B description",
            )
        )

    summary = _quantity_summary(members)
    return DesignResult(
        project_name=plan.project_name,
        layout=layout.name,
        members=members,
        summary=summary,
        assumptions=assumptions,
        questions=questions,
    )


def _common_assumptions() -> list[AssumptionRecord]:
    return [
        AssumptionRecord(
            description="ASD gravity-only sizing; governing combination is D+L for floor members.",
            source="ASCE 7-22 Section 2.4",
        ),
        AssumptionRecord(
            description="Dry service and normal temperature are assumed, so CM = 1.0 and Ct = 1.0.",
            source="Project input and NDS adjustment framework",
        ),
        AssumptionRecord(
            description="Internal calculations use imperial units.", source="Project requirement"
        ),
    ]


def _center_beam_assumption(span_config: str, beam_span_ft: float | None) -> str:
    span_text = f"{beam_span_ft:g} ft" if beam_span_ft is not None else "declared"
    if span_config == "two_span_equal":
        return (
            f"Center beam is modeled as a two-span equal continuous beam with {span_text} spans; "
            "midpoint support receives the interior support reaction from the "
            "continuous-beam model."
        )
    if span_config == "three_span_equal":
        return (
            f"Center beam is modeled as a three-span equal continuous beam with {span_text} spans."
        )
    return (
        f"Center beam is modeled as simple spans of {span_text}; midpoint support receives "
        "reactions from both spans."
    )


def _quantity_summary(members: list[MemberResult]) -> QuantitySummary:
    lumber = 0.0
    glulam = 0.0
    concrete = 0.0
    joists = 0
    footings = 0
    span_count = 1
    for member in members:
        width = member.material.actual_width_in or 0.0
        depth = member.material.actual_depth_in or 0.0
        area_ft2 = width * depth / 144.0
        length = member.length_ft or member.span_ft or 0.0
        if member.member_type == "joist":
            joists += member.quantity
            lumber += area_ft2 * length * member.quantity
        elif member.member_type == "beam":
            span_count = max(span_count, member.trace.span_count or 1)
            if member.material.material_type == "glulam":
                glulam += area_ft2 * length
            else:
                lumber += area_ft2 * length
        elif member.member_type == "column":
            lumber += area_ft2 * length
        elif member.member_type == "spread_footing":
            footings += 1
            width_ft = _trace_value(member, "width")
            length_ft = _trace_value(member, "length")
            thickness_ft = _trace_value(member, "thickness")
            concrete += width_ft * length_ft * thickness_ft
        elif member.member_type == "strip_footing":
            footings += 1
            width_ft = _trace_value(member, "width")
            length_ft = _trace_value(member, "length")
            thickness_ft = _trace_value(member, "thickness")
            concrete += width_ft * length_ft * thickness_ft
    return QuantitySummary(
        lumber_volume_ft3=round(lumber, 3),
        glulam_volume_ft3=round(glulam, 3),
        concrete_volume_ft3=round(concrete, 3),
        joist_count=joists,
        footing_count=footings,
        span_count=span_count,
    )


def _trace_value(member: MemberResult, name: str) -> float:
    for value in member.trace.section_properties:
        if value.name == name:
            return float(value.value)
    raise KeyError(f"{name} missing from {member.member_id}")
