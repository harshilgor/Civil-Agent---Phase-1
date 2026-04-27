"""Plain concrete footing sizing by soil bearing only."""

from civilagent_sizer.members.common import update_trace_governing
from civilagent_sizer.nds.checks import footing_bearing_check
from civilagent_sizer.trace.models import (
    CalculationTrace,
    LoadTrace,
    MaterialSpec,
    MemberResult,
    SourceValue,
)


def size_spread_footing(
    *,
    member_id: str,
    load_lb: float,
    allowable_soil_psf: float,
    thickness_ft: float = 1.0,
) -> MemberResult:
    """Select a square spread footing by IBC 2021 Table 1806.2 soil bearing pressure."""

    for size_ft in _standard_footing_sizes():
        area = size_ft * size_ft
        check = footing_bearing_check(load_lb, allowable_soil_psf, area)
        if check.passed:
            return _make_spread_result(
                member_id, load_lb, allowable_soil_psf, size_ft, thickness_ft, check, True
            )
    size_ft = _standard_footing_sizes()[-1]
    check = footing_bearing_check(load_lb, allowable_soil_psf, size_ft * size_ft)
    return _make_spread_result(
        member_id, load_lb, allowable_soil_psf, size_ft, thickness_ft, check, False
    )


def size_strip_footing(
    *,
    member_id: str,
    line_load_plf: float,
    length_ft: float,
    allowable_soil_psf: float,
    min_width_ft: float = 1.0,
    thickness_ft: float = 1.0,
) -> MemberResult:
    """Size a continuous strip footing by line load and presumptive soil bearing."""

    required_width_ft = line_load_plf / allowable_soil_psf
    width_ft = max(min_width_ft, _ceil_to_increment(required_width_ft, 0.5))
    area = width_ft * 1.0
    check = footing_bearing_check(line_load_plf, allowable_soil_psf, area)
    material = MaterialSpec(
        material_type="concrete", nominal_size=f"{width_ft:.1f} ft strip x {thickness_ft:.1f} ft"
    )
    trace = CalculationTrace(
        member_id=member_id,
        member_type="strip_footing",
        material=material,
        length_ft=length_ft,
        loads=[
            LoadTrace(
                name="line load",
                value=line_load_plf,
                unit="plf",
                source="Tributary floor reaction or minimum perimeter assumption",
            )
        ],
        section_properties=[
            SourceValue(
                name="width",
                value=width_ft,
                unit="ft",
                source="Selected from 6 in footing width increments",
            ),
            SourceValue(
                name="thickness", value=thickness_ft, unit="ft", source="Project assumption"
            ),
            SourceValue(name="length", value=length_ft, unit="ft", source="Project geometry"),
        ],
        checks=[check],
        assumptions=["Plain concrete strip footing checked for soil bearing only."],
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type="strip_footing",
        selected=trace.passed,
        material=material,
        length_ft=length_ft,
        trace=trace,
    )


def _standard_footing_sizes() -> list[float]:
    return [2.0 + 0.5 * index for index in range(9)]


def _ceil_to_increment(value: float, increment: float) -> float:
    steps = int(-(-value // increment))
    return steps * increment


def _make_spread_result(
    member_id: str,
    load_lb: float,
    allowable_soil_psf: float,
    size_ft: float,
    thickness_ft: float,
    check,
    selected: bool,
) -> MemberResult:
    material = MaterialSpec(
        material_type="concrete",
        nominal_size=f"{size_ft:.1f} ft x {size_ft:.1f} ft x {thickness_ft:.1f} ft",
    )
    trace = CalculationTrace(
        member_id=member_id,
        member_type="spread_footing",
        material=material,
        length_ft=size_ft,
        loads=[
            LoadTrace(
                name="concentric axial load",
                value=load_lb,
                unit="lb",
                source="Column or beam support reaction from ASD D+L",
            )
        ],
        section_properties=[
            SourceValue(
                name="width",
                value=size_ft,
                unit="ft",
                source="Standard spread footing catalogue: 2 ft to 6 ft in 6 in increments",
            ),
            SourceValue(
                name="length",
                value=size_ft,
                unit="ft",
                source="Standard spread footing catalogue: 2 ft to 6 ft in 6 in increments",
            ),
            SourceValue(
                name="thickness", value=thickness_ft, unit="ft", source="Project assumption"
            ),
            SourceValue(name="area", value=size_ft * size_ft, unit="ft^2", source="width * length"),
        ],
        checks=[check],
        assumptions=["Plain concrete footing checked for concentric soil bearing only."],
    )
    trace = update_trace_governing(trace)
    return MemberResult(
        member_id=member_id,
        member_type="spread_footing",
        selected=selected and trace.passed,
        material=material,
        length_ft=size_ft,
        trace=trace,
    )
