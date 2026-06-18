"""Shared dataclasses and small utilities for rule-based algorithms."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional


Number = float


def clamp(value: Number, lower: Number = 0.0, upper: Number = 1.0) -> Number:
    return max(lower, min(upper, value))


def dataclass_to_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: dataclass_to_dict(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, tuple):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    return value


@dataclasses.dataclass
class SkillMention:
    mention_id: str
    raw_text: str
    source_type: str
    source_section: str
    evidence_text: str
    evidence_id: Optional[str] = None
    position: Optional[int] = None
    confidence: float = 0.9


@dataclasses.dataclass
class NormalizedSkill:
    skill_id: str
    name: str
    skill_type: str
    aliases: List[str]
    relation_type: str
    evidence_refs: List[str]
    confidence: float


@dataclasses.dataclass
class JDParseResult:
    job_title: str
    job_category: str
    responsibilities: List[str]
    requirements: List[str]
    preferred: List[str]
    education_requirement: Optional[str]
    experience_requirement: Optional[float]
    domain_requirement: List[str]
    raw_skill_mentions: List[SkillMention]
    evidence_items: List[Dict[str, Any]]
    parse_warnings: List[str]


@dataclasses.dataclass
class ResumeParseResult:
    candidate_id: Optional[str]
    education: Optional[str]
    experience_years: float
    target_position: Optional[str]
    work_experiences: List[str]
    projects: List[str]
    certificates: List[str]
    domain_experiences: List[str]
    raw_skill_mentions: List[SkillMention]
    evidence_items: List[Dict[str, Any]]
    parse_warnings: List[str]


@dataclasses.dataclass
class SkillProfile:
    profile_id: str
    profile_type: str
    skills: List[Dict[str, Any]]
    skill_distribution: Dict[str, float]
    vector: List[float]
    metadata: Dict[str, Any]


@dataclasses.dataclass
class ModelAdapterOutput:
    semantic_score: float
    job_embedding: Optional[List[float]]
    resume_embedding: Optional[List[float]]
    skill_contributions: List[Dict[str, Any]]
    item_weights: List[Dict[str, Any]]
    model_explanation: Optional[str]
    model_metadata: Dict[str, Any]


@dataclasses.dataclass
class MatchResult:
    final_score: float
    skill_coverage: float
    distribution_similarity: float
    experience_fit: float
    education_fit: float
    domain_fit: float
    semantic_fit: float
    matched_skills: List[Dict[str, Any]]
    missing_skills: List[Dict[str, Any]]
    insufficient_skills: List[Dict[str, Any]]
    hard_penalties: List[Dict[str, Any]]
    explanation: str


@dataclasses.dataclass
class GapAnalysisResult:
    missing_skills: List[Dict[str, Any]]
    insufficient_skills: List[Dict[str, Any]]
    related_only_skills: List[Dict[str, Any]]
    improvement_suggestions: List[Dict[str, Any]]
    gap_summary: str


@dataclasses.dataclass
class GraphData:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    graph_metadata: Dict[str, Any]
