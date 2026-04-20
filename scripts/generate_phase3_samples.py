"""Generate Phase 3 sample input JSON files into ``data/samples/phase3/``.

Run from the repo root::

    python scripts/generate_phase3_samples.py

Produces three sample inputs that exercise the full Phase 3 pipeline:

    * ``sample_input_office_rc.json``  — 8-story RC office, Chicago
    * ``sample_input_residential_steel.json`` — 6-story steel residential, LA
    * ``sample_input_mixed_occupancy.json`` — 5-story RC mixed-use
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples" / "phase3"


def _rect(width_mm: float, depth_mm: float) -> list[list[float]]:
    return [
        [0.0, 0.0],
        [width_mm, 0.0],
        [width_mm, depth_mm],
        [0.0, depth_mm],
        [0.0, 0.0],
    ]


def _columns(xs: list[float], ys: list[float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    for y in ys:
        for x in xs:
            out.append(
                {
                    "position": [x, y],
                    "grid_intersection": f"G-{i}",
                    "confidence": 1.0,
                    "is_required": False,
                }
            )
            i += 1
    return out


def _supports(cols: list[dict[str, Any]], story_ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    for sid in story_ids:
        for c in cols:
            out.append(
                {
                    "id": f"S{i}-{sid}",
                    "position": c["position"],
                    "story": sid,
                    "classification": "preferred",
                    "score": 0.9,
                    "reasons": [],
                    "penalties": [],
                    "grid_intersection": c["grid_intersection"],
                    "is_stacked": True,
                    "stack_group_id": c["grid_intersection"],
                }
            )
            i += 1
    return out


def _stories(
    n: int, ftf_mm: float, area_m2: float, usages: list[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    elevation = 0.0
    for i in range(n):
        out.append(
            {
                "id": f"S{i + 1}",
                "level": i + 1,
                "floor_to_floor_mm": ftf_mm,
                "elevation_mm": elevation,
                "floor_area_gross_m2": area_m2,
                "usage": usages[i],
            }
        )
        elevation += ftf_mm
    return out


def _building_graph(
    *,
    name: str,
    lat: float,
    lng: float,
    city: str,
    state: str,
    occupancy: str,
    material_pref: str,
    n_stories: int,
    ftf_mm: float,
    width_mm: float,
    depth_mm: float,
    xs: list[float],
    ys: list[float],
    usages: list[str],
) -> dict[str, Any]:
    columns = _columns(xs, ys)
    stories = _stories(n_stories, ftf_mm, (width_mm * depth_mm) / 1_000_000.0, usages)
    return {
        "project": {
            "name": name,
            "location": {"lat": lat, "lng": lng, "city": city, "state": state},
            "occupancy_type": occupancy,
            "material_preference": material_pref,
            "num_stories": n_stories,
            "total_height_mm": ftf_mm * n_stories,
            "building_code": "ASCE 7-22",
        },
        "stories": stories,
        "grid": {
            "x_lines": [{"id": f"X{i}", "position_mm": x} for i, x in enumerate(xs)],
            "y_lines": [{"id": f"Y{i}", "position_mm": y} for i, y in enumerate(ys)],
            "bays": [],
        },
        "walls": [],
        "rooms": [],
        "openings": [],
        "column_candidates": columns,
        "cores": [],
        "facade": {
            "perimeter_polygon": _rect(width_mm, depth_mm),
            "perimeter_length_mm": 2 * (width_mm + depth_mm),
        },
        "metadata": {
            "input_source": "structured_form",
            "confidence_scores": {"overall": 0.9},
            "assumptions_made": [],
            "warnings": [],
        },
    }


def _structural_graph(bg: dict[str, Any]) -> dict[str, Any]:
    story_ids = [s["id"] for s in bg["stories"]]
    return {
        "building_graph_id": bg["project"]["name"],
        "zones": [],
        "support_candidates": _supports(bg["column_candidates"], story_ids),
        "forbidden_regions": [],
        "vertical_alignment_groups": [],
        "span_map": {
            "spans": [],
            "max_span_mm": 9000.0,
            "min_span_mm": 6000.0,
            "typical_span_mm": 8000.0,
            "span_regularity": 1.0,
        },
        "framing_zones": [],
        "gravity_system_candidates": [],
        "lateral_system_candidates": [],
        "constraints": [],
        "metadata": {
            "processing_time_seconds": 0.1,
            "assumptions_made": [],
            "warnings": [],
            "confidence_overall": 0.85,
            "building_regularity": "regular",
            "recommended_review_items": [],
        },
    }


def _sample(
    *,
    filename: str,
    material_family: str,
    risk_category: str,
    exposure_category: str,
    basic_wind_speed: float,
    site_class: str,
    Ss: float,
    S1: float,
    location: dict[str, Any],
    bg: dict[str, Any],
    sg: dict[str, Any],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "building_graph": bg,
        "structural_design_graph": sg,
        "location": location,
        "material_family": material_family,
        "risk_category": risk_category,
        "exposure_category": exposure_category,
        "basic_wind_speed_m_per_s": basic_wind_speed,
        "site_class": site_class,
        "Ss": Ss,
        "S1": S1,
        "overrides": [],
        "building_code": "ASCE 7-22",
    }
    out_path = OUTPUT_DIR / filename
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out_path}")


def main() -> None:
    # 1. Office RC, Chicago
    office_bg = _building_graph(
        name="sample_office_rc",
        lat=41.88, lng=-87.63, city="Chicago", state="IL",
        occupancy="office", material_pref="reinforced_concrete",
        n_stories=8, ftf_mm=3600.0,
        width_mm=4 * 9000.0, depth_mm=3 * 8000.0,
        xs=[9000.0 * i for i in range(5)],
        ys=[8000.0 * i for i in range(4)],
        usages=["office"] * 7 + ["roof_inaccessible"],
    )
    _sample(
        filename="sample_input_office_rc.json",
        material_family="reinforced_concrete",
        risk_category="II",
        exposure_category="B",
        basic_wind_speed=44.7,  # 100 mph
        site_class="D",
        Ss=0.20, S1=0.09,  # low seismic — Chicago
        location={
            "latitude": 41.88, "longitude": -87.63, "city": "Chicago",
            "state_or_region": "IL", "country": "US", "elevation_m": 181.0,
        },
        bg=office_bg, sg=_structural_graph(office_bg),
    )

    # 2. Residential Steel, LA
    res_bg = _building_graph(
        name="sample_residential_steel",
        lat=34.05, lng=-118.24, city="Los Angeles", state="CA",
        occupancy="residential", material_pref="steel",
        n_stories=6, ftf_mm=3200.0,
        width_mm=3 * 6000.0, depth_mm=3 * 6000.0,
        xs=[6000.0 * i for i in range(4)],
        ys=[6000.0 * i for i in range(4)],
        usages=["residential"] * 5 + ["roof_inaccessible"],
    )
    _sample(
        filename="sample_input_residential_steel.json",
        material_family="structural_steel",
        risk_category="II",
        exposure_category="C",
        basic_wind_speed=38.0,  # 85 mph
        site_class="D",
        Ss=1.5, S1=0.6,  # high seismic
        location={
            "latitude": 34.05, "longitude": -118.24, "city": "Los Angeles",
            "state_or_region": "CA", "country": "US", "elevation_m": 71.0,
        },
        bg=res_bg, sg=_structural_graph(res_bg),
    )

    # 3. Mixed occupancy RC
    mixed_bg = _building_graph(
        name="sample_mixed_occupancy",
        lat=40.71, lng=-74.00, city="New York", state="NY",
        occupancy="mixed_use", material_pref="reinforced_concrete",
        n_stories=5, ftf_mm=3800.0,
        width_mm=3 * 8000.0, depth_mm=3 * 8000.0,
        xs=[8000.0 * i for i in range(4)],
        ys=[8000.0 * i for i in range(4)],
        usages=["retail", "office", "office", "office", "roof_inaccessible"],
    )
    _sample(
        filename="sample_input_mixed_occupancy.json",
        material_family="reinforced_concrete",
        risk_category="II",
        exposure_category="B",
        basic_wind_speed=51.4,  # ~115 mph
        site_class="D",
        Ss=0.30, S1=0.08,
        location={
            "latitude": 40.71, "longitude": -74.00, "city": "New York",
            "state_or_region": "NY", "country": "US", "elevation_m": 10.0,
        },
        bg=mixed_bg, sg=_structural_graph(mixed_bg),
    )


if __name__ == "__main__":
    main()
