"""Schemas for person-job matching endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    jd_text: str = Field(..., min_length=1)
    resume_text: str = Field(..., min_length=1)
    use_llm: bool = False


class MatchResponse(BaseModel):
    final_score: float = 0.0
    decision: str = ""
    matched_skills: List[Dict[str, Any]] = Field(default_factory=list)
    missing_skills: List[Dict[str, Any]] = Field(default_factory=list)
    partial_skills: List[Dict[str, Any]] = Field(default_factory=list)
    score_detail: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    graph: Dict[str, Any] = Field(default_factory=dict)
    jd_parse: Dict[str, Any] = Field(default_factory=dict)
    resume_parse: Dict[str, Any] = Field(default_factory=dict)
    match_result: Dict[str, Any] = Field(default_factory=dict)
    llm_used: bool = False
    llm_status: Dict[str, Any] = Field(default_factory=dict)
