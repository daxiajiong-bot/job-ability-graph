"""Request schemas for all v3 resources."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.domain.entities import DocumentType


class DocumentSourceRequest(BaseModel):
    source_system: str = Field(default="manual", min_length=1, max_length=120)
    external_id: Optional[str] = Field(default=None, max_length=200)
    uri: Optional[str] = Field(default=None, max_length=2048)
    published_at: Optional[str] = Field(default=None, max_length=64)


class DocumentCreateRequest(BaseModel):
    document_type: DocumentType
    text: str = Field(min_length=1, max_length=2_000_000)
    source: DocumentSourceRequest = Field(default_factory=DocumentSourceRequest)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


class ProfileCreateRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)


class DocumentRetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    document_ids: list[str] = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be blank")
        return query


class KnowledgeGraphCreateRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    candidate_profile_ids: list[str] = Field(default_factory=list)
    job_profile_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_a_source(self) -> "KnowledgeGraphCreateRequest":
        if not (self.document_ids or self.candidate_profile_ids or self.job_profile_ids):
            raise ValueError("at least one source resource is required")
        return self


class GraphRetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    seed_entity_ids: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)


class PositionDiscoveryRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class PositionDeltaRequest(BaseModel):
    baseline_job_profile_id: str = Field(min_length=1, max_length=128)
    current_job_profile_id: str = Field(min_length=1, max_length=128)
    supporting_document_ids: list[str] = Field(default_factory=list)


class MatchOptions(BaseModel):
    include_document_evidence: bool = True
    include_graph_evidence: bool = True


class MatchCreateRequest(BaseModel):
    candidate_profile_id: str = Field(min_length=1, max_length=128)
    job_profile_id: str = Field(min_length=1, max_length=128)
    options: MatchOptions = Field(default_factory=MatchOptions)


class ReportCreateRequest(BaseModel):
    match_id: str = Field(min_length=1, max_length=128)
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
