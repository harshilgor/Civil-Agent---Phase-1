"""Pure demand/capacity checks for NDS-style member sizing."""

from civilagent_sizer.trace.models import CodeCheck


def simple_uniform_moment(w_plf: float, span_ft: float) -> float:
    """Return maximum simple-span moment ``wL^2/8`` in inch-pounds."""

    return w_plf * span_ft**2 / 8.0 * 12.0


def simple_uniform_shear(w_plf: float, span_ft: float) -> float:
    """Return maximum simple-span end shear ``wL/2`` in pounds."""

    return w_plf * span_ft / 2.0


def simple_uniform_deflection(w_plf: float, span_ft: float, e_psi: float, ix_in4: float) -> float:
    """Return simple-span uniform-load deflection ``5wL^4/(384EI)`` in inches."""

    w_lbin = w_plf / 12.0
    span_in = span_ft * 12.0
    return 5.0 * w_lbin * span_in**4 / (384.0 * e_psi * ix_in4)


def bending_check(moment_inlb: float, fb_prime_psi: float, sx_in3: float) -> CodeCheck:
    """Check flexure per NDS 2018 3.3.1."""

    capacity = fb_prime_psi * sx_in3
    ratio = moment_inlb / capacity if capacity > 0 else float("inf")
    return CodeCheck(
        name="bending",
        demand=moment_inlb,
        capacity=capacity,
        unit="in-lb",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="NDS 2018 3.3.1",
        equation="M <= F'b * S",
        details={"fb_prime_psi": fb_prime_psi, "sx_in3": sx_in3},
    )


def shear_check(shear_lb: float, fv_prime_psi: float, area_in2: float) -> CodeCheck:
    """Check rectangular-section shear per NDS 2018 3.4.2."""

    capacity = (2.0 / 3.0) * fv_prime_psi * area_in2
    ratio = shear_lb / capacity if capacity > 0 else float("inf")
    return CodeCheck(
        name="shear",
        demand=shear_lb,
        capacity=capacity,
        unit="lb",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="NDS 2018 3.4.2",
        equation="V <= (2/3) * F'v * A",
        details={"fv_prime_psi": fv_prime_psi, "area_in2": area_in2},
    )


def deflection_check(
    deflection_in: float,
    span_ft: float,
    limit_ratio: int,
    load_case: str,
) -> CodeCheck:
    """Check member deflection against IBC 2021 Table 1604.3 floor limits."""

    limit = span_ft * 12.0 / limit_ratio
    ratio = deflection_in / limit if limit > 0 else float("inf")
    return CodeCheck(
        name=f"deflection_{load_case}",
        demand=deflection_in,
        capacity=limit,
        unit="in",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="IBC 2021 Table 1604.3",
        equation=f"Delta_{load_case} <= L/{limit_ratio}",
        details={"span_ft": span_ft, "limit_ratio": limit_ratio},
    )


def bearing_check(
    reaction_lb: float, fc_perp_prime_psi: float, bearing_area_in2: float
) -> CodeCheck:
    """Check compression perpendicular to grain at bearing per NDS 2018 3.10."""

    capacity = fc_perp_prime_psi * bearing_area_in2
    ratio = reaction_lb / capacity if capacity > 0 else float("inf")
    return CodeCheck(
        name="bearing",
        demand=reaction_lb,
        capacity=capacity,
        unit="lb",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="NDS 2018 3.10",
        equation="R <= F'c_perp * A_bearing",
        details={"fc_perp_prime_psi": fc_perp_prime_psi, "bearing_area_in2": bearing_area_in2},
    )


def axial_check(axial_lb: float, fc_prime_psi: float, area_in2: float) -> CodeCheck:
    """Check axial compression parallel to grain per NDS 2018 3.7.1."""

    capacity = fc_prime_psi * area_in2
    ratio = axial_lb / capacity if capacity > 0 else float("inf")
    return CodeCheck(
        name="axial_compression",
        demand=axial_lb,
        capacity=capacity,
        unit="lb",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="NDS 2018 3.7.1",
        equation="P <= F'c * A",
        details={"fc_prime_psi": fc_prime_psi, "area_in2": area_in2},
    )


def footing_bearing_check(load_lb: float, allowable_soil_psf: float, area_ft2: float) -> CodeCheck:
    """Check footing soil bearing pressure using IBC 2021 Table 1806.2 values."""

    pressure = load_lb / area_ft2
    ratio = pressure / allowable_soil_psf if allowable_soil_psf > 0 else float("inf")
    return CodeCheck(
        name="soil_bearing",
        demand=pressure,
        capacity=allowable_soil_psf,
        unit="psf",
        ratio=ratio,
        passed=ratio <= 1.0,
        source="IBC 2021 Table 1806.2",
        equation="q = P / A <= q_allow",
        details={"load_lb": load_lb, "area_ft2": area_ft2},
    )
