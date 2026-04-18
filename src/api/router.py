"""Main API router — aggregates all sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from .structured_input import router as structured_router
from .cad_upload import router as cad_router
from .image_upload import router as image_router
from .graph_output import router as graph_router
from .structural_output import router as structural_router

api_router = APIRouter()

api_router.include_router(structured_router, prefix="/building", tags=["Structured Input"])
api_router.include_router(cad_router, prefix="/building/upload", tags=["CAD Upload"])
api_router.include_router(image_router, prefix="/building/upload", tags=["Image Upload"])
api_router.include_router(graph_router, prefix="/building", tags=["Building Graph"])
api_router.include_router(structural_router, prefix="/building", tags=["Structural Graph"])
