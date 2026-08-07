from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SkillLevel = Literal["required", "preferred", "mentioned"]
DocumentType = Literal["job"]
ValidationStatus = Literal["valid", "invalid", "needs_review"]


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    level: SkillLevel
    evidence: str

    @field_validator("name", "evidence")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        return value.strip()


class TextConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    evidence: str | None = None


class IntConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | None = None
    evidence: str | None = None


class JDConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    education: TextConstraint = Field(default_factory=TextConstraint)
    experience_years: IntConstraint = Field(default_factory=IntConstraint)
    location: TextConstraint = Field(default_factory=TextConstraint)


class JDProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["jd_profile_v1"] = "jd_profile_v1"
    document_id: str
    document_type: DocumentType = "job"
    title: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    constraints: JDConstraints = Field(default_factory=JDConstraints)
    raw_text: str

    @field_validator("document_id")
    @classmethod
    def document_id_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("document_id is required")
        return value


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    status: ValidationStatus
    profile: JDProfile | None = None
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class SerializedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    status: ValidationStatus
    serialized_text: str


class BatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = 0
    valid: int = 0
    invalid: int = 0
    needs_review: int = 0
    failed: int = 0
    skipped: int = 0
    output_dir: str
    notes: dict[str, Any] = Field(default_factory=dict)

