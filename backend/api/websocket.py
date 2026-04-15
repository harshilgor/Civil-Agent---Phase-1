"""WebSocket /ws/jobs/{id} — progress push during pipeline execution."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.deps import get_job_service

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    job_svc = get_job_service()
    try:
        while True:
            rec = job_svc.get_job(job_id)
            if rec:
                await websocket.send_text(
                    json.dumps(
                        {
                            "job_id": job_id,
                            "status": rec.status.value,
                            "progress_pct": rec.progress_pct,
                            "current_stage": rec.current_stage,
                        },
                    ),
                )
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
