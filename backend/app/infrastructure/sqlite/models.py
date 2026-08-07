"""Data models for SQLite rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class UserRow:
    user_id: str
    created_at: str
    last_active_at: str


@dataclass(frozen=True)
class DocumentRow:
    id: str
    user_id: str
    document_type: str
    text: str
    title: Optional[str] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    skills: Optional[str] = None  # JSON array string
    source_system: str = "manual"
    source_id: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[str] = None  # JSON object string
    content_digest: str = ""
    created_at: str = ""

    def to_public(self) -> dict[str, Any]:
        """Public representation (no raw text exposed)."""
        import json

        skills_list = []
        if self.skills:
            try:
                skills_list = json.loads(self.skills)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "id": self.id,
            "document_id": self.id,
            "document_type": self.document_type,
            "title": self.title,
            "company_name": self.company_name,
            "industry": self.industry,
            "location": self.location,
            "salary_range": self.salary_range,
            "experience": self.experience,
            "education": self.education,
            "skills": skills_list,
            "source": {"source_system": self.source_system, "source_id": self.source_id},
            "url": self.url,
            "text_length": len(self.text) if self.text else 0,
            "content_digest": self.content_digest,
            "created_at": self.created_at,
            "user_id": self.user_id,
        }


@dataclass(frozen=True)
class ProfileRow:
    id: str
    user_id: str
    document_id: str
    profile_type: str
    state: str
    attributes: Optional[str] = None  # JSON
    evidence: Optional[str] = None  # JSON
    warnings: Optional[str] = None  # JSON
    implementation: Optional[str] = None
    artifacts: Optional[str] = None  # JSON
    created_at: str = ""

    def to_public(self) -> dict[str, Any]:
        import json

        def _parse_json(raw: Optional[str], default: Any = None) -> Any:
            if not raw:
                return default if default is not None else []
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return default if default is not None else []

        return {
            "id": self.id,
            "profile_id": self.id,
            "profile_type": self.profile_type,
            "document_id": self.document_id,
            "state": self.state,
            "attributes": _parse_json(self.attributes, {}),
            "evidence": _parse_json(self.evidence, []),
            "warnings": _parse_json(self.warnings, []),
            "implementation": self.implementation or "mock",
            "artifacts": _parse_json(self.artifacts, {}),
            "created_at": self.created_at,
        }
