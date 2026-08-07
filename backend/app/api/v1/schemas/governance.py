"""Request schemas for data governance endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from backend.app.domain.entities import DocumentType


class GovernanceRegisterPathRequest(BaseModel):
    document_type: DocumentType
    path: str = Field(min_length=1, max_length=4096)
    source_system: str = Field(default="local_path", min_length=1, max_length=120)
    external_id: Optional[str] = Field(default=None, max_length=200)
    uri: Optional[str] = Field(default=None, max_length=2048)
    published_at: Optional[str] = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceProcessRequest(BaseModel):
    version: Optional[int] = Field(default=None, ge=1)


class GovernanceRetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    doc_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be blank")
        return query
