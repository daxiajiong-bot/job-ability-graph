"""LLM output field schemas for future JSON validation."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class JDExtractionOutput(TypedDict, total=False):
    position_name: str
    category: str
    domain: List[str]
    required_skills: List[Dict[str, Any]]
    preferred_skills: List[Dict[str, Any]]
    responsibilities: List[str]
    required_level: Dict[str, Any]
    evidence: List[Dict[str, Any]]


class ResumeExtractionOutput(TypedDict, total=False):
    candidate_name: str
    target_position: str
    education: str
    experience_years: float
    skills: List[Dict[str, Any]]
    projects: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    confidence: float


class MatchExplanationOutput(TypedDict, total=False):
    match_reasons: List[str]
    risks: List[str]
    ability_gaps: List[str]
    improvement_suggestions: List[str]
    evidence_refs: List[str]


class EmergingPositionOutput(TypedDict, total=False):
    position_name: str
    capability_mix: List[str]
    core_skills: List[str]
    responsibility_patterns: List[str]
    scenario_changes: List[str]
    evidence: List[Dict[str, Any]]
    confidence: float


class PositionUpdateOutput(TypedDict, total=False):
    new_skills: List[str]
    rising_skills: List[str]
    declining_skills: List[str]
    change_reasons: List[str]
    evidence: List[Dict[str, Any]]


LLM_OUTPUT_SCHEMAS = {
    "jd_extraction": JDExtractionOutput,
    "resume_extraction": ResumeExtractionOutput,
    "match_explanation": MatchExplanationOutput,
    "emerging_position": EmergingPositionOutput,
    "position_update": PositionUpdateOutput,
}
