from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal["job", "policy", "industry_report", "occupational_standard"]
ParseStatus = Literal["parsed", "needs_ocr", "failed"]
ReviewStatus = Literal["candidate", "needs_review", "approved", "rejected"]
AbilityCategory = Literal["K", "S", "Tech", "T", "L", "Skill", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpec(StrictModel):
    source_id: str
    source_type: SourceType
    input: str
    input_format: Literal["auto", "jsonl", "csv", "pdf", "html", "docx", "txt", "url"] = "auto"
    source_name: str
    publisher: str | None = None
    published_at: datetime | None = None
    collected_at: datetime | None = None
    license: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "input", "source_name")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class SourceManifest(StrictModel):
    schema_version: Literal["source_manifest_v1"] = "source_manifest_v1"
    sources: list[SourceSpec]

    @model_validator(mode="after")
    def unique_source_ids(self) -> "SourceManifest":
        values = [source.source_id for source in self.sources]
        if len(values) != len(set(values)):
            raise ValueError("source_id values must be unique")
        return self


class ExternalDocument(StrictModel):
    schema_version: Literal["external_document_v1"] = "external_document_v1"
    document_id: str
    source_type: SourceType
    source_name: str
    title: str
    text: str
    raw_sha256: str
    parser_version: str
    parse_status: ParseStatus = "parsed"
    publisher: str | None = None
    uri: str | None = None
    external_id: str | None = None
    company: str | None = None
    industry: str | None = None
    region: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("document_id", "source_name", "title", "raw_sha256", "parser_version")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class Evidence(StrictModel):
    schema_version: Literal["evidence_v1"] = "evidence_v1"
    evidence_id: str
    document_id: str
    source_type: SourceType
    text: str
    text_sha256: str
    uri: str | None = None
    page: int | None = None
    section: str | None = None
    char_start: int | None = None
    char_end: int | None = None

    @model_validator(mode="after")
    def valid_span(self) -> "Evidence":
        if self.char_start is not None and self.char_end is not None:
            if self.char_start < 0 or self.char_end <= self.char_start:
                raise ValueError("invalid evidence character span")
        return self


class ExtractedFact(StrictModel):
    schema_version: Literal["extracted_fact_v1"] = "extracted_fact_v1"
    fact_id: str
    document_id: str
    fact_type: Literal[
        "job_title",
        "responsibility",
        "required_skill",
        "preferred_skill",
        "mentioned_skill",
        "industry_signal",
        "policy_signal",
    ]
    value: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    extractor: str


class JobObservation(StrictModel):
    schema_version: Literal["job_observation_v1"] = "job_observation_v1"
    observation_id: str
    document_id: str
    source_name: str
    title: str
    normalized_title: str
    company: str | None = None
    industry: str | None = None
    region: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    mentioned_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    exact_cluster_id: str
    near_dup_cluster_id: str
    snapshot_week: str


class AbilityRef(StrictModel):
    source_schema: str
    source_node_id: str | None = None
    category: AbilityCategory = "unknown"
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    resolution_status: Literal["exact", "curated_alias", "review_candidate", "unresolved"]
    resolution_score: float | None = Field(default=None, ge=0.0, le=1.0)


class TrendWindow(StrictModel):
    recent_start: datetime
    recent_end: datetime
    baseline_start: datetime
    baseline_end: datetime


class TrendMetrics(StrictModel):
    distinct_job_count: int = 0
    previous_distinct_job_count: int = 0
    distinct_company_count: int = 0
    distinct_source_count: int = 0
    distinct_region_count: int = 0
    recent_share: float = 0.0
    baseline_share: float = 0.0
    growth_rate: float = 0.0
    share_delta: float = 0.0
    ewma_slope: float = 0.0
    robust_zscore: float = 0.0
    persistence: float = 0.0
    source_diversity: float = 0.0
    propagation_count: int = 0


class TrendFeature(StrictModel):
    schema_version: Literal["trend_feature_v1"] = "trend_feature_v1"
    trend_id: str
    entity_type: Literal["ability", "job_role"]
    entity_name: str
    kg_node_id: str | None = None
    window: TrendWindow
    metrics: TrendMetrics
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class RoleAbility(StrictModel):
    name: str
    category: AbilityCategory = "unknown"
    role: Literal["required", "preferred", "mentioned"]
    kg_node_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]


class EmergingRoleScores(StrictModel):
    novelty: float = Field(ge=0.0, le=1.0)
    growth: float = Field(ge=0.0, le=1.0)
    persistence: float = Field(ge=0.0, le=1.0)
    source_diversity: float = Field(ge=0.0, le=1.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)


class EmergingRole(StrictModel):
    schema_version: Literal["emerging_role_v1"] = "emerging_role_v1"
    role_id: str
    canonical_title: str
    aliases: list[str] = Field(default_factory=list)
    core_responsibilities: list[str]
    required_skills: list[RoleAbility]
    preferred_skills: list[RoleAbility]
    typical_industry_scenarios: list[str]
    industries: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    supporting_job_count: int
    supporting_company_count: int
    supporting_source_count: int
    scores: EmergingRoleScores
    evidence_ids: list[str]
    status: ReviewStatus = "candidate"
    explanation: str


class SkillChange(StrictModel):
    skill_name: str
    kg_node_id: str | None = None
    change_type: Literal["added", "rising", "modified", "declining", "removal_candidate"]
    baseline_share: float
    recent_share: float
    share_delta: float
    relative_lift: float
    p_value: float | None = None
    q_value: float | None = None
    supporting_company_count: int
    evidence_ids: list[str]


class JobSkillUpdate(StrictModel):
    schema_version: Literal["job_skill_update_v1"] = "job_skill_update_v1"
    update_id: str
    canonical_role: str
    kg_job_ids: list[str] = Field(default_factory=list)
    window: TrendWindow
    changes: list[SkillChange]
    evidence_ids: list[str]
    status: ReviewStatus = "candidate"
    explanation: str


class KGLinkDelta(StrictModel):
    schema_version: Literal["trend_kg_delta_v1"] = "trend_kg_delta_v1"
    delta_id: str
    baseline_graph_fingerprint: str
    operation: Literal["link_existing", "propose_node", "propose_edge"]
    source_id: str
    target_id: str | None = None
    relation_type: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    resolution_status: Literal["exact", "curated_alias", "review_candidate", "unresolved"]
    properties: dict[str, Any] = Field(default_factory=dict)


class ArtifactInfo(StrictModel):
    path: str
    sha256: str
    records: int | None = None


class RunManifest(StrictModel):
    schema_version: Literal["jobtrend_run_manifest_v1"] = "jobtrend_run_manifest_v1"
    run_id: str
    created_at: datetime
    status: Literal["prepared", "running", "completed", "failed"]
    config_sha256: str
    baseline_graph_fingerprint: str | None = None
    input_artifacts: list[ArtifactInfo] = Field(default_factory=list)
    output_artifacts: list[ArtifactInfo] = Field(default_factory=list)
    model_ids: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_cny: float = 0.0
    counts: dict[str, int] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(StrictModel):
    object_type: Literal["emerging_role", "job_skill_update", "ability_mapping"]
    object_id: str
    decision: Literal["approved", "rejected", "needs_review"]
    canonical_title: str | None = None
    reviewer: str
    reviewed_at: datetime
    notes: str | None = None
