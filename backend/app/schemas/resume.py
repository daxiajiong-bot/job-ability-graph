"""Schemas for resume parsing endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ResumeParseRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1)
    resume_text: Optional[str] = Field(None, min_length=1)
    use_llm: bool = False
    save_artifacts: bool = True  # 是否保存中间产物


class ResumeDocumentParseRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., min_length=1)
    use_llm: bool = False
    save_artifacts: bool = True  # 是否保存中间产物


class ResumeParseResponse(BaseModel):
    mode: str = "resume_parse"
    resume_parse: Dict[str, Any] = Field(default_factory=dict)
    resume_profile: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    competition_hooks: Dict[str, Any] = Field(default_factory=dict)


class ResumeDocumentParseResponse(BaseModel):
    mode: str = "resume_document_parse"
    document: Dict[str, Any] = Field(default_factory=dict)
    resume_parse: Dict[str, Any] = Field(default_factory=dict)
    resume_profile: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    competition_hooks: Dict[str, Any] = Field(default_factory=dict)
