"""Schemas for emerging position and position update endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceDocumentRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_id: Optional[str] = None
    source_type: str = "jd"
    collected_at: Optional[str] = None
    reliability: float = Field(0.8, ge=0.0, le=1.0)


class EmergingJobRequest(BaseModel):
    source_documents: List[SourceDocumentRequest] = Field(..., min_length=1)
    use_llm: bool = False


class PositionUpdateRequest(BaseModel):
    old_jd_text: str = Field(..., min_length=1)
    new_jd_text: str = Field(..., min_length=1)
    use_llm: bool = False


class EvolutionResponse(BaseModel):
    mode: str
    data: Dict[str, Any] = Field(default_factory=dict)
