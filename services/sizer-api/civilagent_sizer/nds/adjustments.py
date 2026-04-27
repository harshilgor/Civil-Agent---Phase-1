"""NDS adjustment-factor functions.

Implemented clauses are limited to ASD gravity checks used by the prototype. Each public
function corresponds to a cited NDS provision or table in the returned trace data.
"""

from dataclasses import dataclass
from math import sqrt

from civilagent_sizer.catalogue.loader import load_yaml
from civilagent_sizer.trace.models import AdjustmentFactorTrace

PROPERTY_SYMBOLS = {
    "fb": "Fb",
    "ft": "Ft",
    "fv": "Fv",
    "fc_perp": "Fc_perp",
    "fc": "Fc",
    "e": "E",
    "emin": "Emin",
}


@dataclass(frozen=True)
class AdjustmentSet:
    """Adjusted design value multipliers and trace records for sawn lumber."""

    fb: float
    fv: float
    fc_perp: float
    fc: float
    e: float
    emin: float
    traces: tuple[AdjustmentFactorTrace, ...]


def _nominal_depth(nominal: str) -> int:
    return int(nominal.lower().split("x", maxsplit=1)[1].split(".", maxsplit=1)[0])


def _nominal_thickness(nominal: str) -> int:
    return int(nominal.lower().split("x", maxsplit=1)[0].split(".", maxsplit=1)[0])


def load_duration_factor(load_combination: str) -> AdjustmentFactorTrace:
    """Return ``CD`` for an ASD load combination per NDS 2018 Table 2.3.2."""

    general = load_yaml("adjustment_factors/general.yaml")["load_duration"]
    mapping = {"D": 0.90, "D+L": 1.00, "D+S": 1.15, "D+0.75L+0.75S": 1.15}
    value = mapping[load_combination]
    return AdjustmentFactorTrace(
        symbol="CD",
        name="Load duration factor",
        value=value,
        applies_to=["Fb", "Ft", "Fv", "Fc"],
        source=general["source"],
        confidence=general["confidence"],
        note=f"Combination {load_combination}",
    )


def temperature_factor() -> AdjustmentFactorTrace:
    """Return normal-temperature ``Ct = 1.0`` per NDS 2018 Table 2.3.3."""

    table = load_yaml("adjustment_factors/general.yaml")["temperature"]
    return AdjustmentFactorTrace(
        symbol="Ct",
        name="Temperature factor",
        value=1.0,
        applies_to=["Fb", "Ft", "Fv", "Fc_perp", "Fc", "E", "Emin"],
        source=table["source"],
        confidence=table["confidence"],
        note="Normal-temperature residential interior assumption.",
    )


def wet_service_factor() -> AdjustmentFactorTrace:
    """Return dry-service ``CM = 1.0`` per NDS service-condition adjustment framework."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["wet_service_factor"]
    return AdjustmentFactorTrace(
        symbol="CM",
        name="Wet service factor",
        value=1.0,
        applies_to=["Fb", "Ft", "Fv", "Fc_perp", "Fc", "E", "Emin"],
        source=table["source"],
        confidence=table["confidence"],
        note="Wet-service reductions are out of scope for this dry residential sample.",
    )


def wet_service_factor_for_property(
    property_name: str,
    *,
    wet_service: bool,
    reference_times_cf_psi: float | None = None,
) -> AdjustmentFactorTrace:
    """Return sawn-lumber ``CM`` including NDS 2018 Table 4.3.1 footnote exceptions."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["wet_service_factor"]
    factors = table["wet_service"] if wet_service else table["dry_service"]
    value = float(factors[property_name])
    note = "Dry service; CM = 1.0."
    if wet_service:
        note = f"Moisture content > {table['service_moisture_threshold_percent']}% in service."
        exception = table.get("exceptions", {}).get(property_name)
        if exception and reference_times_cf_psi is not None:
            threshold = float(exception["threshold_psi"])
            if reference_times_cf_psi <= threshold:
                value = float(exception["value"])
                note = f"{note} Exception applied: {exception['condition']}"
    return AdjustmentFactorTrace(
        symbol="CM",
        name="Wet service factor",
        value=value,
        applies_to=[PROPERTY_SYMBOLS[property_name]],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def incising_factor(property_name: str, incised: bool) -> AdjustmentFactorTrace:
    """Return ``Ci`` for incised or non-incised sawn lumber per NDS 2018 4.3.8."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["incising_factor"]
    key = "incised" if incised else "not_incised"
    value = float(table[key][property_name])
    return AdjustmentFactorTrace(
        symbol="Ci",
        name="Incising factor",
        value=value,
        applies_to=[PROPERTY_SYMBOLS[property_name]],
        source=table["source"],
        confidence=table["confidence"],
        note="Project input incised=true." if incised else "Non-incised lumber assumption.",
    )


def size_factor(species: str, nominal: str, property_name: str) -> AdjustmentFactorTrace:
    """Return sawn dimension-lumber ``CF`` per NDS Supplement Table 4A adjustment factors."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["size_factor"]
    if species in table["applies_to_species_except"]:
        value = 1.0
        note = "Southern Pine table values are treated as size-specific; CF = 1.0."
    else:
        depth = _nominal_depth(nominal)
        rows = table["rows"]
        row = rows[-1]
        for candidate in rows:
            if depth <= int(candidate["nominal_depth_in"]):
                row = candidate
                break
        value = float(row[property_name])
        note = f"Nominal depth {depth} in."
    return AdjustmentFactorTrace(
        symbol="CF",
        name="Size factor",
        value=value,
        applies_to=[PROPERTY_SYMBOLS[property_name]],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def flat_use_factor(nominal: str, edgewise: bool = True) -> AdjustmentFactorTrace:
    """Return ``Cfu`` for dimension lumber per NDS 2018 4.3.6."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["flat_use_factor"]
    if edgewise:
        value = 1.0
        note = "Member is loaded edgewise; flat-use factor does not increase Fb."
    else:
        depth = _nominal_depth(nominal)
        thickness = _nominal_thickness(nominal)
        row = table["rows"][-1]
        for candidate in table["rows"]:
            if depth <= int(candidate["nominal_depth_in"]):
                row = candidate
                break
        key = "thickness_4" if thickness == 4 else "thickness_2_or_3"
        value = float(row[key] or 1.0)
        note = "Flatwise bending."
    return AdjustmentFactorTrace(
        symbol="Cfu",
        name="Flat use factor",
        value=value,
        applies_to=["Fb"],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def repetitive_member_factor(spacing_in: float, enabled: bool) -> AdjustmentFactorTrace:
    """Return ``Cr`` for repetitive floor members per NDS 2018 4.3.9."""

    table = load_yaml("adjustment_factors/sawn_lumber.yaml")["repetitive_member_factor"]
    qualifies = enabled and spacing_in <= float(table["max_spacing_in"])
    return AdjustmentFactorTrace(
        symbol="Cr",
        name="Repetitive member factor",
        value=float(table["value"]) if qualifies else 1.0,
        applies_to=["Fb"],
        source=table["source"],
        confidence=table["confidence"],
        note="Joists at not more than 24 in o.c. with load-distributing sheathing."
        if qualifies
        else "Repetitive member conditions not used.",
    )


def bearing_area_factor(
    bearing_length_in: float, at_member_end: bool = True
) -> AdjustmentFactorTrace:
    """Return ``Cb`` for compression perpendicular to grain per NDS 2018 3.10.4."""

    table = load_yaml("adjustment_factors/general.yaml")["bearing_area_factor"]
    if at_member_end or bearing_length_in >= 6.0:
        value = 1.0
        note = "End bearing or bearing length >= 6 in; conservative Cb = 1.0."
    else:
        value = (bearing_length_in + 0.375) / bearing_length_in
        note = "Interior bearing length less than 6 in."
    return AdjustmentFactorTrace(
        symbol="Cb",
        name="Bearing area factor",
        value=value,
        applies_to=["Fc_perp"],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def beam_stability_factor(
    fb_star_psi: float,
    emin_prime_psi: float,
    actual_width_in: float,
    actual_depth_in: float,
    unbraced_length_in: float,
    compression_edge_braced: bool = True,
) -> AdjustmentFactorTrace:
    """Compute ``CL`` for bending members per NDS 2018 3.3.3."""

    table = load_yaml("adjustment_factors/general.yaml")["beam_stability"]
    if compression_edge_braced or actual_depth_in / actual_width_in <= 2.0:
        value = 1.0
        note = "Compression edge braced or d/b <= 2; CL = 1.0."
    else:
        rb = sqrt(unbraced_length_in * actual_depth_in / (actual_width_in**2))
        if rb > float(table["slenderness_limit_rb"]):
            value = 0.0
            note = f"RB = {rb:.3f} exceeds limit {table['slenderness_limit_rb']}."
        else:
            fbe = float(table["fbe_coefficient"]) * emin_prime_psi / (rb**2)
            a_ratio = fbe / fb_star_psi
            c = float(table["ylinen_c"])
            value = ((1 + a_ratio) / (2 * c)) - sqrt(((1 + a_ratio) / (2 * c)) ** 2 - (a_ratio / c))
            note = f"RB = {rb:.3f}; FbE = {fbe:.3f} psi."
    return AdjustmentFactorTrace(
        symbol="CL",
        name="Beam stability factor",
        value=value,
        applies_to=["Fb"],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def column_stability_factor(
    fc_star_psi: float,
    emin_prime_psi: float,
    actual_width_in: float,
    actual_depth_in: float,
    unbraced_length_in: float,
    material_type: str = "sawn_lumber",
    effective_length_factor: float = 1.0,
) -> AdjustmentFactorTrace:
    """Compute ``CP`` for axial compression members per NDS 2018 3.7.1."""

    table = load_yaml("adjustment_factors/general.yaml")["column_stability"]
    slenderness_x = effective_length_factor * unbraced_length_in / actual_depth_in
    slenderness_y = effective_length_factor * unbraced_length_in / actual_width_in
    slenderness = max(slenderness_x, slenderness_y)
    if slenderness > float(table["slenderness_limit"]):
        value = 0.0
        note = f"le/d = {slenderness:.3f} exceeds limit {table['slenderness_limit']}."
    else:
        fce = float(table["fce_coefficient"]) * emin_prime_psi / (slenderness**2)
        c = float(table["c_glulam"] if material_type == "glulam" else table["c_sawn_lumber"])
        a_ratio = fce / fc_star_psi
        value = ((1 + a_ratio) / (2 * c)) - sqrt(((1 + a_ratio) / (2 * c)) ** 2 - (a_ratio / c))
        note = f"le/d = {slenderness:.3f}; FcE = {fce:.3f} psi."
    return AdjustmentFactorTrace(
        symbol="CP",
        name="Column stability factor",
        value=value,
        applies_to=["Fc"],
        source=table["source"],
        confidence=table["confidence"],
        note=note,
    )


def glulam_volume_factor(span_ft: float, depth_in: float, width_in: float) -> AdjustmentFactorTrace:
    """Compute glulam ``CV`` per NDS 2018 5.3.6."""

    table = load_yaml("adjustment_factors/general.yaml")["glulam_volume_factor"]
    exponent = 1.0 / float(table["x_exponent"])
    k_l = float(table.get("k_l_uniform_load", 1.0))
    value = k_l * (21.0 / span_ft) ** exponent * (12.0 / depth_in) ** exponent
    value *= (5.125 / width_in) ** exponent
    value = min(value, 1.0)
    return AdjustmentFactorTrace(
        symbol="CV",
        name="Glulam volume factor",
        value=value,
        applies_to=["Fb"],
        source=table["source"],
        confidence=table["confidence"],
        note=f"K_L={k_l}; span={span_ft} ft, d={depth_in} in, b={width_in} in.",
    )


def lvl_volume_factor(span_ft: float, depth_in: float, width_in: float) -> AdjustmentFactorTrace:
    """Compute Microllam LVL ``CV`` from verified manufacturer depth/thickness factors."""

    depth_factor = min((12.0 / depth_in) ** 0.136, 1.18)
    thickness_factor = min((1.75 / width_in) ** 0.136, 1.0)
    value = depth_factor * thickness_factor
    return AdjustmentFactorTrace(
        symbol="CV",
        name="Microllam LVL volume factor",
        value=value,
        applies_to=["Fb"],
        source=(
            "Weyerhaeuser Microllam LVL verified data; "
            "CV_depth=(12/d)^0.136 max 1.18 and CV_thickness=(1.75/t)^0.136 max 1.0"
        ),
        confidence="very_high",
        note=(
            f"span={span_ft} ft recorded for trace; d={depth_in} in gives "
            f"CV_depth={depth_factor:.4f}; t={width_in} in gives "
            f"CV_thickness={thickness_factor:.4f}; combined CV={value:.4f}."
        ),
    )


def lvl_tension_length_factor(length_ft: float) -> AdjustmentFactorTrace:
    """Return Microllam LVL ``Ft`` length adjustment for members over 4 ft long."""

    value = (4.0 / length_ft) ** 0.085 if length_ft > 4.0 else 1.0
    return AdjustmentFactorTrace(
        symbol="C_Ft_length",
        name="Microllam LVL tension length adjustment",
        value=value,
        applies_to=["Ft"],
        source="Weyerhaeuser Microllam LVL verified data; Ft adjusted by (4/L)^0.085 for L > 4 ft",
        confidence="very_high",
        note=f"L={length_ft} ft.",
    )


def lvl_repetitive_member_factor(width_in: float) -> AdjustmentFactorTrace:
    """Return LVL ``Cr`` for built-up multi-ply members per NDS 2018 Section 8.3."""

    value = 1.04 if width_in > 1.75 else 1.0
    return AdjustmentFactorTrace(
        symbol="Cr",
        name="LVL repetitive member factor",
        value=value,
        applies_to=["Fb"],
        source="NDS 2018 Section 8.3; LVL multi-ply Cr from verified reference prompt",
        confidence="medium",
        note="Cr = 1.04 for multi-ply LVL; single-ply LVL uses Cr = 1.0.",
    )


def sawn_lumber_adjustments(
    *,
    species: str,
    nominal: str,
    load_combination: str,
    spacing_in: float | None,
    repetitive: bool,
    incised: bool,
    bearing_length_in: float,
    at_bearing_end: bool,
    compression_edge_braced: bool,
    fb_ref_psi: float,
    fc_ref_psi: float,
    emin_ref_psi: float,
    width_in: float,
    depth_in: float,
    unbraced_length_in: float,
    apply_size_factor: bool = True,
) -> AdjustmentSet:
    """Build adjusted value multipliers for sawn lumber per NDS 2018 Tables 2.3.1/4A."""

    cd = load_duration_factor(load_combination)
    cm = wet_service_factor()
    ct = temperature_factor()
    ci_fb = incising_factor("fb", incised)
    ci_fv = incising_factor("fv", incised)
    ci_fc_perp = incising_factor("fc_perp", incised)
    ci_fc = incising_factor("fc", incised)
    ci_e = incising_factor("e", incised)
    ci_emin = incising_factor("emin", incised)
    if apply_size_factor:
        cf_fb = size_factor(species, nominal, "fb")
        cf_fc = size_factor(species, nominal, "fc")
    else:
        cf_fb = AdjustmentFactorTrace(
            symbol="CF",
            name="Size factor",
            value=1.0,
            applies_to=["Fb"],
            source=(
                "NDS 2018 Supplement Table 4D; timber values are used without dimension-lumber CF"
            ),
            confidence="medium",
            note="Dimension-lumber size factor disabled for timber entry.",
        )
        cf_fc = AdjustmentFactorTrace(
            symbol="CF",
            name="Size factor",
            value=1.0,
            applies_to=["Fc"],
            source=(
                "NDS 2018 Supplement Table 4D; timber values are used without dimension-lumber CF"
            ),
            confidence="medium",
            note="Dimension-lumber size factor disabled for timber entry.",
        )
    cfu = flat_use_factor(nominal, edgewise=True)
    cr = repetitive_member_factor(spacing_in or 999.0, repetitive)
    cb = bearing_area_factor(bearing_length_in, at_member_end=at_bearing_end)
    e_multiplier = cm.value * ct.value * ci_e.value
    emin_multiplier = cm.value * ct.value * ci_emin.value
    fb_star = fb_ref_psi * cd.value * cm.value * ct.value * cf_fb.value * ci_fb.value * cr.value
    cl = beam_stability_factor(
        fb_star_psi=fb_star,
        emin_prime_psi=emin_ref_psi * emin_multiplier,
        actual_width_in=width_in,
        actual_depth_in=depth_in,
        unbraced_length_in=unbraced_length_in,
        compression_edge_braced=compression_edge_braced,
    )
    fc_star = fc_ref_psi * cd.value * cm.value * ct.value * cf_fc.value * ci_fc.value
    cp = column_stability_factor(
        fc_star_psi=fc_star,
        emin_prime_psi=emin_ref_psi * emin_multiplier,
        actual_width_in=width_in,
        actual_depth_in=depth_in,
        unbraced_length_in=unbraced_length_in,
        material_type="sawn_lumber",
    )
    traces = (
        cd,
        cm,
        ct,
        cf_fb,
        cfu,
        ci_fb,
        cr,
        cl,
        ci_fv,
        ci_fc_perp,
        cb,
        cf_fc,
        ci_fc,
        cp,
        ci_e,
        ci_emin,
    )
    return AdjustmentSet(
        fb=cd.value
        * cm.value
        * ct.value
        * cl.value
        * cf_fb.value
        * cfu.value
        * ci_fb.value
        * cr.value,
        fv=cd.value * cm.value * ct.value * ci_fv.value,
        fc_perp=cm.value * ct.value * ci_fc_perp.value * cb.value,
        fc=cd.value * cm.value * ct.value * cf_fc.value * ci_fc.value * cp.value,
        e=e_multiplier,
        emin=emin_multiplier,
        traces=traces,
    )
