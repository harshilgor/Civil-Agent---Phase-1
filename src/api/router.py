"""Main API router — aggregates all sub-routers.

Phase 3 (Load & Assumption Engine) is fenced behind the ``PHASE3_ENABLED``
feature flag (see :mod:`src.config`).  When the flag is ``False`` (default),
the Phase 3 router is neither imported nor mounted, so the larger Phase 3
dependency surface stays out of the Phase 1 build.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.config import settings

from .cad_upload import router as cad_router
from .graph_output import router as graph_router
from .image_upload import router as image_router
from .jobs import router as jobs_router
from .structural_output import router as structural_router
from .structured_input import router as structured_router

api_router = APIRouter()

api_router.include_router(structured_router, prefix="/building", tags=["Structured Input"])
api_router.include_router(cad_router, prefix="/building/upload", tags=["CAD Upload"])
api_router.include_router(image_router, prefix="/building/upload", tags=["Image Upload"])
api_router.include_router(graph_router, prefix="/building", tags=["Building Graph"])
api_router.include_router(structural_router, prefix="/building", tags=["Structural Graph"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])

if settings.phase3_enabled:
    # Lazy import so the Phase 3 module (and its transitive deps) only loads
    # when the flag is on.  Keeps Phase 1 boot time and import surface small.
    from src.phase3.api.router import phase3_router  # noqa: PLC0415

    api_router.include_router(phase3_router, prefix="/phase3", tags=["Phase 3"])
