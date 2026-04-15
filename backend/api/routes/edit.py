"""PATCH /jobs/{id}/rooms/{room_id} — polygon, relabel, merge/split hints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.api.deps import get_edit_service, get_job_service
from backend.services.edit_service import EditService
from backend.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["edit"])


class RoomPatchBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    polygon: list[list[float]] | None = None
    label: str | None = None
    merge_with: str | None = None
    split_line: list[list[float]] | None = None


@router.patch("/{job_id}/rooms/{room_id}")
async def patch_room(
    job_id: str,
    room_id: str,
    body: RoomPatchBody,
    job_svc: JobService = Depends(get_job_service),
    edits: EditService = Depends(get_edit_service),
) -> dict:
    rec = job_svc.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = body.model_dump(exclude_none=True)
    return edits.apply_room_patch(job_id, room_id, payload)
