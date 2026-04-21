"""Phase 3 router aggregator — mounted by :mod:`src.api.router`."""

from __future__ import annotations

from fastapi import APIRouter

from .endpoints import router as endpoints_router

phase3_router = APIRouter()
phase3_router.include_router(endpoints_router)
