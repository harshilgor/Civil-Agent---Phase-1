"""Tributary load helpers for rectangular residential floors."""

from math import floor


def joist_count(length_perpendicular_to_span_ft: float, spacing_in: float) -> int:
    """Return the number of joists for a rectangular bay with joists at fixed spacing."""

    spacing_ft = spacing_in / 12.0
    return floor(length_perpendicular_to_span_ft / spacing_ft) + 1


def joist_reaction_plf(area_load_psf: float, joist_span_ft: float) -> float:
    """Return line reaction on a supporting wall/beam from simple-span joists."""

    return area_load_psf * joist_span_ft / 2.0


def joist_end_reaction_lb(area_load_psf: float, spacing_in: float, joist_span_ft: float) -> float:
    """Return one joist end reaction from uniform floor load on one joist."""

    tributary_width_ft = spacing_in / 12.0
    line_load_plf = area_load_psf * tributary_width_ft
    return line_load_plf * joist_span_ft / 2.0


def support_line_load_from_joists(
    joist_count_value: int,
    area_load_psf: float,
    spacing_in: float,
    joist_span_ft: float,
    support_length_ft: float,
    supported_end_fraction: float = 1.0,
) -> float:
    """Return footing line load from accumulated joist reactions on one support line."""

    total_reaction_lb = (
        joist_count_value
        * joist_end_reaction_lb(area_load_psf, spacing_in, joist_span_ft)
        * supported_end_fraction
    )
    return total_reaction_lb / support_length_ft
