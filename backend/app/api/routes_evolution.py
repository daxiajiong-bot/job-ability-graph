"""Emerging job and position ability evolution API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.evolution import EmergingJobRequest, EvolutionResponse, PositionUpdateRequest
from backend.app.services.evolution_service import discover_position, update_position


router = APIRouter()


@router.post("/evolution/discover", response_model=EvolutionResponse)
def discover_endpoint(payload: EmergingJobRequest) -> EvolutionResponse:
    source_documents = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in payload.source_documents]
    try:
        result = discover_position(source_documents, use_llm=payload.use_llm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to discover emerging job") from exc
    return EvolutionResponse(mode=result.get("mode", "emerging_job_discovery"), data=result)


@router.post("/evolution/update", response_model=EvolutionResponse)
def update_endpoint(payload: PositionUpdateRequest) -> EvolutionResponse:
    old_jd_text = payload.old_jd_text.strip()
    new_jd_text = payload.new_jd_text.strip()
    if not old_jd_text or not new_jd_text:
        raise HTTPException(status_code=400, detail="old_jd_text and new_jd_text must not be empty")
    try:
        result = update_position(old_jd_text=old_jd_text, new_jd_text=new_jd_text, use_llm=payload.use_llm)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to compare job versions") from exc
    return EvolutionResponse(mode=result.get("mode", "job_update_analysis"), data=result)


@router.post("/jobs/discover", response_model=EvolutionResponse)
def discover_job_alias(payload: EmergingJobRequest) -> EvolutionResponse:
    return discover_endpoint(payload)


@router.post("/jobs/compare", response_model=EvolutionResponse)
def compare_job_alias(payload: PositionUpdateRequest) -> EvolutionResponse:
    return update_endpoint(payload)
