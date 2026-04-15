"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from backend.api.middleware.cors import setup_cors
from backend.api.middleware.error_handler import setup_error_handlers
from backend.api.routes import diagnostics, edit, export, jobs, results, scale, upload
from backend.api.websocket import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Civil Agent API", version="0.1.0")
    setup_cors(app)
    setup_error_handlers(app)

    app.include_router(upload.router)
    app.include_router(jobs.router)
    app.include_router(results.router)
    app.include_router(edit.router)
    app.include_router(diagnostics.router)
    app.include_router(export.router)
    app.include_router(scale.router)
    app.include_router(ws_router)

    return app


app = create_app()
