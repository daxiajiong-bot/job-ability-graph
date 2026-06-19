"""Schemas for graph endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GraphResponse(BaseModel):
    graph_id: str = ""
    version: str = ""
    generated_at: str = ""
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphViewResponse(GraphResponse):
    view_type: str = ""


class JobGraphDocumentRequest(BaseModel):
    id: Optional[str] = None
    text: str = Field(..., min_length=1)
    level: Optional[str] = None
    seniority: Optional[str] = None
    source_type: str = "jd"


class PanoramaGraphRequest(BaseModel):
    job_documents: List[JobGraphDocumentRequest] = Field(..., min_length=1)


class FlexibleResponse(BaseModel):
    mode: str
    data: Dict[str, Any] = Field(default_factory=dict)
