"""Stable schemas for data-governed graph RAG artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentMetadata:
    doc_id: str
    version: int
    document_type: str
    source_system: str
    original_filename: str
    raw_path: str
    content_hash: str
    byte_size: int
    mime_type: str | None
    created_at: str
    status: str
    external_id: str | None = None
    source_uri: str | None = None
    duplicate_of: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityReport:
    doc_id: str
    version: int
    status: str
    checks: list[dict[str, Any]]
    warnings: list[str]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedDocument:
    doc_id: str
    version: int
    document_type: str
    parser: str
    raw_path: str
    content_hash: str
    text: str
    sections: list[dict[str, Any]]
    warnings: list[str]
    created_at: str

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_text:
            data.pop("text", None)
            data["char_count"] = len(self.text)
        return data


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    version: int
    sequence: int
    text: str
    start_char: int
    end_char: int
    content_hash: str
    raw_path: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    doc_id: str
    version: int
    chunk_id: str
    quote: str
    start_char: int
    end_char: int
    source_field: str
    raw_path: str
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntityCandidate:
    entity_candidate_id: str
    doc_id: str
    version: int
    chunk_id: str
    entity_type: str
    surface: str
    normalized_name: str
    normalized_id: str
    category: str | None
    lskt_label: str | None
    start_char: int
    end_char: int
    confidence: float
    extraction_method: str
    evidence: Evidence
    created_at: str
    esco_id: str | None = None
    esco_uri: str | None = None
    esco_preferred_label: str | None = None
    esco_version: str | None = None
    linking_status: str = "unmapped"
    linking_confidence: float = 0.0
    normalization_status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationCandidate:
    relation_candidate_id: str
    doc_id: str
    version: int
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    evidence: Evidence
    validation_status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    doc_id: str
    version: int
    label: str
    properties: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    doc_id: str
    version: int
    source_id: str
    target_id: str
    relation_type: str
    evidence_ids: list[str]
    evidence: list[Evidence]
    properties: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
