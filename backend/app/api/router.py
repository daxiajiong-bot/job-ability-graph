"""Compatibility router that aggregates the split API route modules."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.routes_evolution import router as evolution_router
from backend.app.api.routes_graph import router as graph_router
from backend.app.api.routes_match import match
from backend.app.api.routes_match import router as match_router
from backend.app.api.routes_parse import samples
from backend.app.api.routes_parse import router as parse_router


router = APIRouter()
router.include_router(parse_router)
router.include_router(match_router)
router.include_router(graph_router)
router.include_router(evolution_router)


__all__ = ["router", "samples", "match"]
