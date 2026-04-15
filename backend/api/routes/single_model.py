"""Single-model demo: upload → one adapter → PNGs on disk + JSON (scrappy UI)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from backend.pipeline.single_model_run import (
    get_active_model_name,
    run_single_model_for_active_branch,
)

router = APIRouter(prefix="/single-model", tags=["single-model"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRAPPY_PAGE = PROJECT_ROOT / "frontend" / "public" / "single-model-scrappy.html"


@router.get("/active-model")
async def active_model() -> dict[str, str]:
    return {"active_model": get_active_model_name()}


@router.get("/ui", response_class=HTMLResponse)
async def single_model_ui() -> HTMLResponse:
    if not SCRAPPY_PAGE.is_file():
        return HTMLResponse("<pre>missing frontend/public/single-model-scrappy.html</pre>", status_code=404)
    return HTMLResponse(SCRAPPY_PAGE.read_text(encoding="utf-8"))


@router.post("/run")
async def single_model_run(file: UploadFile = File(...)) -> dict:
    run_id = uuid.uuid4().hex
    suffix = Path(file.filename or "upload").suffix or ".png"
    uploads = PROJECT_ROOT / "data" / "single_model_uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / f"{run_id}{suffix}"
    dest.write_bytes(await file.read())
    return run_single_model_for_active_branch(dest, run_id)


@router.get("/artifacts/{run_id}/{filename}")
async def get_artifact(run_id: str, filename: str) -> FileResponse:
    safe = Path(filename).name
    path = PROJECT_ROOT / "data" / "single_model_outputs" / run_id / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)
