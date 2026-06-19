"""Graph API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.graph import FlexibleResponse, GraphResponse, GraphViewResponse, PanoramaGraphRequest
from backend.app.services.graph_service import build_panorama, get_full_graph, get_graph_view


router = APIRouter()


@router.get("/graph/full", response_model=GraphResponse)
def graph_full() -> GraphResponse:
    return GraphResponse(**get_full_graph())


@router.get("/graph/view", response_model=GraphViewResponse)
def graph_view(view_type: str = Query(..., pattern="^(position|tech_stack|level|match|evolution)$")) -> GraphViewResponse:
    try:
        graph = get_graph_view(view_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphViewResponse(**graph, view_type=view_type)


@router.post("/graph/panorama", response_model=FlexibleResponse)
def panorama_graph_endpoint(payload: PanoramaGraphRequest) -> FlexibleResponse:
    job_documents = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in payload.job_documents]
    try:
        result = build_panorama(job_documents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to build panorama graph") from exc
    return FlexibleResponse(mode=result.get("mode", "job_skill_panorama_graph"), data=result)
