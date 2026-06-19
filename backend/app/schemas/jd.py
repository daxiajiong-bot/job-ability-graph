"""Schemas for JD parsing endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JDParseRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1)
    jd_text: Optional[str] = Field(None, min_length=1)
    use_llm: bool = False
    save_artifacts: bool = True  # 是否保存中间产物


class JDParseResponse(BaseModel):
    mode: str = "jd_parse"
    jd_parse: Dict[str, Any] = Field(default_factory=dict)
    job_profile: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    competition_hooks: Dict[str, Any] = Field(default_factory=dict)
