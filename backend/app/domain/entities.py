"""Dependency-free entities for the formal v3 resource contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4


class DocumentType(str, Enum):
    RESUME = "resume"
    JD = "jd"
    POLICY = "policy"
    INDUSTRY_REPORT = "industry_report"
    MARKET_DATA = "market_data"


class ProfileType(str, Enum):
    CANDIDATE = "candidate"
    JOB = "job"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resource_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class SourceDocument:
    id: str
    document_type: DocumentType
    text: str
    source: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    content_digest: str

    @classmethod
    def create(
        cls,
        document_type: DocumentType,
        text: str,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> "SourceDocument":
        return cls(
            id=resource_id("doc"),
            document_type=document_type,
            text=text,
            source=source,
            metadata=metadata,
            created_at=utc_now(),
            content_digest=sha256(text.encode("utf-8")).hexdigest(),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_type": self.document_type.value,
            "source": self.source,
            "metadata": self.metadata,
            "char_count": len(self.text),
            "content_digest": self.content_digest,
            "created_at": self.created_at,
            "storage": "memory",
        }


@dataclass(frozen=True)
class Profile:
    id: str
    profile_type: ProfileType
    source_document_id: str
    state: str
    attributes: dict[str, Any]
    evidence: list[dict[str, Any]]
    warnings: list[str]
    implementation: str
    created_at: str
    artifacts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        profile_type: ProfileType,
        source_document_id: str,
        result: dict[str, Any],
    ) -> "Profile":
        return cls(
            id=resource_id("candidate_profile" if profile_type is ProfileType.CANDIDATE else "job_profile"),
            profile_type=profile_type,
            source_document_id=source_document_id,
            state=str(result["state"]),
            attributes=dict(result.get("attributes", {})),
            evidence=list(result.get("evidence", [])),
            warnings=list(result.get("warnings", [])),
            implementation=str(result.get("implementation", "mock")),
            created_at=utc_now(),
            artifacts=dict(result.get("artifacts", {})),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_type": self.profile_type.value,
            "source_document_id": self.source_document_id,
            "state": self.state,
            "attributes": self.attributes,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "implementation": self.implementation,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class KnowledgeGraphSnapshot:
    id: str
    document_ids: list[str]
    candidate_profile_ids: list[str]
    job_profile_ids: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    state: str
    implementation: str
    created_at: str

    @classmethod
    def create(
        cls,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
        result: dict[str, Any],
    ) -> "KnowledgeGraphSnapshot":
        return cls(
            id=resource_id("graph"),
            document_ids=list(document_ids),
            candidate_profile_ids=list(candidate_profile_ids),
            job_profile_ids=list(job_profile_ids),
            nodes=list(result.get("nodes", [])),
            edges=list(result.get("edges", [])),
            state=str(result["state"]),
            implementation=str(result.get("implementation", "mock")),
            created_at=utc_now(),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema": "position-skill-capability/v1",
            "document_ids": self.document_ids,
            "candidate_profile_ids": self.candidate_profile_ids,
            "job_profile_ids": self.job_profile_ids,
            "nodes": self.nodes,
            "edges": self.edges,
            "state": self.state,
            "implementation": self.implementation,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class MatchAssessment:
    id: str
    candidate_profile_id: str
    job_profile_id: str
    score: Optional[float]
    decision: str
    strengths: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    learning_path: list[dict[str, Any]]
    document_evidence: list[dict[str, Any]]
    graph_evidence: list[dict[str, Any]]
    state: str
    implementation: str
    created_at: str
    details: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        candidate_profile_id: str,
        job_profile_id: str,
        result: dict[str, Any],
    ) -> "MatchAssessment":
        return cls(
            id=resource_id("match"),
            candidate_profile_id=candidate_profile_id,
            job_profile_id=job_profile_id,
            score=result.get("score"),
            decision=str(result["decision"]),
            strengths=list(result.get("strengths", [])),
            gaps=list(result.get("gaps", [])),
            learning_path=list(result.get("learning_path", [])),
            document_evidence=list(result.get("document_evidence", [])),
            graph_evidence=list(result.get("graph_evidence", [])),
            state=str(result["state"]),
            implementation=str(result.get("implementation", "mock")),
            created_at=utc_now(),
            details=dict(result.get("details", {})),
            summary=str(result.get("summary", "")),
            warnings=list(result.get("warnings", [])),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_profile_id": self.candidate_profile_id,
            "job_profile_id": self.job_profile_id,
            "score": self.score,
            "decision": self.decision,
            "strengths": self.strengths,
            "gaps": self.gaps,
            "learning_path": self.learning_path,
            "document_evidence": self.document_evidence,
            "graph_evidence": self.graph_evidence,
            "state": self.state,
            "implementation": self.implementation,
            "created_at": self.created_at,
            "details": self.details,
            "summary": self.summary,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class GeneratedReport:
    id: str
    match_id: str
    language: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    state: str = "not_implemented"
    implementation: str = "mock"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, match_id: str, language: str, result: dict[str, Any]) -> "GeneratedReport":
        return cls(
            id=resource_id("report"),
            match_id=match_id,
            language=language,
            sections=list(result.get("sections", [])),
            state=str(result["state"]),
            implementation=str(result.get("implementation", "mock")),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "match_id": self.match_id,
            "language": self.language,
            "sections": self.sections,
            "state": self.state,
            "implementation": self.implementation,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Task:
    id: str
    task_type: str
    status: TaskStatus
    document_id: str
    profile_id: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, task_type: str, document_id: str) -> "Task":
        now = utc_now()
        return cls(
            id=resource_id("task"),
            task_type=task_type,
            status=TaskStatus.PENDING,
            document_id=document_id,
            created_at=now,
            updated_at=now,
        )

    def public(self) -> dict[str, Any]:
        return {
            "task_id": self.id,
            "status": self.status.value,
            "task_type": self.task_type,
            "document_id": self.document_id,
            "profile_id": self.profile_id,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
