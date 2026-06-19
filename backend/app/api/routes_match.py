"""Matching API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.match import MatchRequest, MatchResponse
from backend.app.services.match_service import run_match


router = APIRouter()


@router.post("/match", response_model=MatchResponse)
def match(payload: MatchRequest) -> MatchResponse:
    jd_text = payload.jd_text.strip()
    resume_text = payload.resume_text.strip()
    if not jd_text or not resume_text:
        raise HTTPException(status_code=400, detail="jd_text and resume_text must not be empty")
    try:
        return MatchResponse(**run_match(jd_text=jd_text, resume_text=resume_text, use_llm=payload.use_llm, save_artifacts=payload.save_artifacts))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to run matcher") from exc
