"""FastAPI wrapper for the civilagent-sizer engine."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from civilagent_sizer import __version__ as SIZER_VERSION
from civilagent_sizer.layout import size_plan_layout
from civilagent_sizer.schemas import PlanInput


ENGINE_NAME = "civilagent-sizer"
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "https://civil-agent.com",
]

app = FastAPI(title="Civil Agent Sizer API", version=SIZER_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "SIZER_API_CORS_ORIGINS",
            ",".join(DEFAULT_ALLOWED_ORIGINS),
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):3\d{3}$",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": ENGINE_NAME, "version": SIZER_VERSION}


@app.post("/api/v1/size")
def size_project(payload: dict[str, Any]) -> dict[str, Any]:
    plan, layout_name = _plan_and_layout_from_payload(payload)
    try:
        result = size_plan_layout(plan, layout_name)
    except (ValueError, KeyError) as exc:
        raise _invalid_input(str(exc)) from exc
    return _with_cost_estimate(result.model_dump(mode="json"))


@app.post("/api/v1/size/compare")
def compare_layouts(payload: dict[str, Any]) -> dict[str, Any]:
    plan, _layout_name = _plan_and_layout_from_payload(payload, default_layout="A")

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(size_plan_layout, plan, "A")
            future_b = executor.submit(size_plan_layout, plan, "B")
            layout_a = _with_cost_estimate(future_a.result().model_dump(mode="json"))
            layout_b = _with_cost_estimate(future_b.result().model_dump(mode="json"))
    except (ValueError, KeyError) as exc:
        raise _invalid_input(str(exc)) from exc

    cost_a = _total_cost(layout_a)
    cost_b = _total_cost(layout_b)
    volume_a = _lumber_volume(layout_a)
    volume_b = _lumber_volume(layout_b)
    cheaper = "A" if cost_a <= cost_b else "B"

    return {
        "layout_a": layout_a,
        "layout_b": layout_b,
        "comparison": {
            "cost_difference_dollars": round(abs(cost_a - cost_b), 2),
            "cheaper_layout": cheaper,
            "lumber_volume_difference_ft3": round(abs(volume_a - volume_b), 3),
        },
    }


@app.post("/api/v1/export/pdf")
def export_pdf(result: dict[str, Any]) -> Response:
    try:
        pdf = _render_pdf(result)
    except Exception as exc:  # pragma: no cover - defensive HTTP boundary
        raise HTTPException(
            status_code=422,
            detail={"error": {"message": f"Could not render PDF: {exc}", "type": "export_error"}},
        ) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="civil-agent-calculations.pdf"'},
    )


def _plan_and_layout_from_payload(
    payload: dict[str, Any],
    *,
    default_layout: str | None = None,
) -> tuple[PlanInput, str]:
    layout_name = str(
        payload.get("layout")
        or payload.get("selected_layout")
        or payload.get("layout_name")
        or default_layout
        or "A"
    ).upper()
    plan_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"layout", "selected_layout", "layout_name"}
    }

    if "dimensions" not in plan_payload or "layouts" not in plan_payload:
        plan_payload = _simplified_payload_to_plan(payload)

    try:
        return PlanInput.model_validate(plan_payload), layout_name
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"message": "Invalid sizer input.", "type": "validation_error", "issues": exc.errors()}},
        ) from exc


def _simplified_payload_to_plan(payload: dict[str, Any]) -> dict[str, Any]:
    length_ft = float(payload.get("room_length_ft") or payload.get("length_ft") or 24.0)
    width_ft = float(payload.get("room_width_ft") or payload.get("width_ft") or 16.0)
    beam_span_ft = length_ft / 2.0
    joist_spacing_in = float(payload.get("joist_spacing_in") or 16.0)
    loads = payload.get("load_parameters") or {}
    load_parameters = {
        "dead_load_psf": float(payload.get("dead_load_psf") or loads.get("dead_load_psf") or 15.0),
        "live_load_psf": float(payload.get("live_load_psf") or loads.get("live_load_psf") or 40.0),
        "species": payload.get("species") or loads.get("species") or "Douglas Fir-Larch",
        "grade": payload.get("grade") or loads.get("grade") or "No. 2",
        "beam_material_preference": (
            payload.get("beam_material_preference")
            or loads.get("beam_material_preference")
            or "any"
        ),
    }

    return {
        "project_name": payload.get("project_name") or "Untitled wood framing project",
        "dimensions": {"length_ft": length_ft, "width_ft": width_ft},
        "load_parameters": load_parameters,
        "layouts": [
            {
                "name": "A",
                "layout_type": "perimeter_support",
                "joist_span_ft": width_ft,
                "joist_spacing_in": joist_spacing_in,
                "description": "Joists span the room width and bear on perimeter supports.",
            },
            {
                "name": "B",
                "layout_type": "center_beam",
                "joist_span_ft": width_ft / 2.0,
                "joist_spacing_in": joist_spacing_in,
                "beam_span_ft": beam_span_ft,
                "beam_total_length_ft": length_ft,
                "beam_tributary_width_ft": width_ft / 2.0,
                "beam_span_config": "two_span_equal",
                "description": "Center beam creates two joist bays and has one midpoint column.",
            },
        ],
    }


def _invalid_input(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": {"message": message, "type": "sizing_input_error"}},
    )


def _with_cost_estimate(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.setdefault("summary", {})
    lumber_ft3 = float(summary.get("lumber_volume_ft3") or 0.0)
    glulam_ft3 = float(summary.get("glulam_volume_ft3") or 0.0)
    concrete_ft3 = float(summary.get("concrete_volume_ft3") or 0.0)
    member_count = _member_count(result)
    lumber = round((lumber_ft3 * 12.0 * 2.75) + (glulam_ft3 * 12.0 * 7.5), 2)
    concrete = round(concrete_ft3 * 15.0, 2)
    hardware = round(max(125.0, member_count * 18.0), 2)
    summary["cost_estimate"] = {
        "lumber_installed_dollars": lumber,
        "concrete_dollars": concrete,
        "hardware_dollars": hardware,
        "total_dollars": round(lumber + concrete + hardware, 2),
        "currency": "USD",
    }
    return result


def _member_count(result: dict[str, Any]) -> int:
    return sum(int(member.get("quantity") or 1) for member in result.get("members", []))


def _total_cost(result: dict[str, Any]) -> float:
    return float(result.get("summary", {}).get("cost_estimate", {}).get("total_dollars") or 0.0)


def _lumber_volume(result: dict[str, Any]) -> float:
    summary = result.get("summary", {})
    return float(summary.get("lumber_volume_ft3") or 0.0) + float(summary.get("glulam_volume_ft3") or 0.0)


def _render_pdf(result: dict[str, Any]) -> bytes:
    lines = _calculation_lines(result)
    return _simple_pdf(lines)


def _calculation_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        "Civil Agent Wood Framing Calculation Package",
        f"Project: {result.get('project_name', 'Untitled project')}",
        f"Layout: {result.get('layout', '-')}",
        "Codes: NDS 2018 / IBC 2021 / ASCE 7-22",
        "",
    ]
    for member in result.get("members", []):
        trace = member.get("trace", {})
        mat = member.get("material", {})
        lines.extend(
            [
                f"MEMBER {member.get('member_id', '-')}",
                f"Type: {member.get('member_type', '-')}",
                f"Selected: {mat.get('nominal_size', '-')} {mat.get('species') or ''} {mat.get('grade') or ''}".strip(),
                f"Span: {member.get('span_ft') or '-'} ft    Quantity: {member.get('quantity', 1)}",
                "LOADS",
            ]
        )
        for item in trace.get("loads", []):
            lines.append(
                f"  {item.get('name', '-')}: {_fmt(item.get('value'))} {item.get('unit') or ''}    {item.get('source') or ''}"
            )
        lines.append("SECTION PROPERTIES")
        for item in trace.get("section_properties", []):
            lines.append(
                f"  {item.get('name', '-')}: {_fmt(item.get('value'))} {item.get('unit') or ''}    {item.get('source') or ''}"
            )
        lines.append("REFERENCE DESIGN VALUES")
        for item in trace.get("reference_design_values", []):
            lines.append(
                f"  {item.get('name', '-')}: {_fmt(item.get('value'))} {item.get('unit') or ''}    {item.get('source') or ''}"
            )
        lines.append("ADJUSTMENT FACTORS")
        for item in trace.get("adjustment_factors", []):
            lines.append(
                f"  {item.get('symbol', '-')}: {_fmt(item.get('value'))}    {item.get('name') or ''}    {item.get('source') or ''}"
            )
        lines.append("CODE CHECKS")
        for check in trace.get("checks", []):
            mark = "PASS" if check.get("passed") else "FAIL"
            lines.append(
                f"  {check.get('name', '-')}: demand {_fmt(check.get('demand'))} / capacity {_fmt(check.get('capacity'))} "
                f"{check.get('unit') or ''}; ratio {_fmt(check.get('ratio'))} {mark}"
            )
        lines.extend(
            [
                f"Governing: {trace.get('governing_check') or '-'} at {_fmt(trace.get('final_utilization'))}",
                "",
            ]
        )
    footer = "Produced by Civil Agent. Engineer of record responsible for review and stamping."
    lines.append(footer)
    return lines


def _simple_pdf(lines: list[str]) -> bytes:
    pages: list[list[str]] = []
    page: list[str] = []
    for line in lines:
        if len(page) >= 58:
            pages.append(page)
            page = []
        page.append(line)
    if page:
        pages.append(page)

    out = BytesIO()
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_lines in pages:
        content = _page_stream(page_lines)
        content_ids.append(add(content))
        page_ids.append(0)

    pages_id_placeholder = len(objects) + len(pages) + 1
    for idx, content_id in enumerate(content_ids):
        page_ids[idx] = add(
            (
                f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
                f"/MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{idx} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_start = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return out.getvalue()


def _page_stream(lines: list[str]) -> bytes:
    footer = "Produced by Civil Agent. Engineer of record responsible for review and stamping."
    commands = ["BT", "/F1 9 Tf", "50 750 Td", "12 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line[:118])}) Tj")
        commands.append("T*")
    commands.extend(["ET", "BT", "/F1 7 Tf", f"50 28 Td ({_pdf_escape(footer)}) Tj", "ET"])
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    return b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    return str(value)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("SIZER_API_PORT", "8001")))
