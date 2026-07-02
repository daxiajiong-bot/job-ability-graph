"""Mocks that expose future seams without producing fake intelligence."""

from __future__ import annotations

from typing import Any

from backend.app.domain.entities import KnowledgeGraphSnapshot, MatchAssessment, Profile, ProfileType, SourceDocument
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION


NOT_IMPLEMENTED = "not_implemented"


def _mock(reason: str, **payload: Any) -> dict[str, Any]:
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "reason": reason,
        **payload,
    }


class MockStructuredExtractor:
    def extract(self, document: SourceDocument) -> dict[str, Any]:
        return _mock("Structured extraction is reserved for a future local LLM.", fields={}, evidence=[])


class MockSkillNormalizer:
    def normalize(self, extraction: dict[str, Any]) -> dict[str, Any]:
        return _mock("Skill normalization is not configured.", skills=[])


class MockProfileBuilder:
    def build(
        self,
        profile_type: ProfileType,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "profile_schema": PROFILE_SCHEMA_VERSION,
            "skills": [],
            "capabilities": [],
            "experience": [],
            "education": [],
            "projects": [],
        }
        if profile_type is ProfileType.JOB:
            attributes.update({"job": {}, "job_title": None, "requirements": [], "responsibilities": [], "jd_profile": {}})
        else:
            attributes.update({"candidate": {}, "career_intent": {}, "target_position": None, "resume_profile": {}})
        return _mock(
            "Profile construction is reserved for structured extraction and normalization adapters.",
            attributes=attributes,
            evidence=[],
            warnings=["No extraction, normalization, or inference has been performed."],
        )


class MockDocumentRetriever:
    def retrieve(self, query: str, document_ids: list[str], filters: dict[str, Any]) -> dict[str, Any]:
        return _mock("Document RAG is not configured.", query=query, document_ids=document_ids, evidence=[])


class MockKnowledgeGraphBuilder:
    def build(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]:
        return _mock("Neo4j graph construction is not configured.", nodes=[], edges=[])


class MockGraphRetriever:
    def retrieve(
        self,
        graph: KnowledgeGraphSnapshot,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]:
        return _mock("GraphRAG is not configured.", query=query, entities=[], paths=[])


class MockPositionEvolution:
    def discover(self, document_ids: list[str], options: dict[str, Any]) -> dict[str, Any]:
        return _mock(
            "New-position discovery is not configured.",
            document_ids=document_ids,
            candidate_positions=[],
            evidence=[],
        )

    def delta(
        self,
        baseline: Profile,
        current: Profile,
        supporting_document_ids: list[str],
    ) -> dict[str, Any]:
        return _mock(
            "Position evolution analysis is not configured.",
            baseline_job_profile_id=baseline.id,
            current_job_profile_id=current.id,
            added=[],
            removed=[],
            changed=[],
            evidence=[],
        )


class MockMatcher:
    def assess(self, candidate: Profile, job: Profile, options: dict[str, Any]) -> dict[str, Any]:
        return _mock(
            "Graph-enhanced person-job matching is not configured.",
            score=None,
            decision="not_evaluated",
            strengths=[],
            gaps=[],
            learning_path=[],
            document_evidence=[],
            graph_evidence=[],
        )


class MockReportGenerator:
    def generate(self, match: MatchAssessment, language: str) -> dict[str, Any]:
        return _mock("Report generation is reserved for a future local LLM.", sections=[])


def capability_catalog(
    *,
    structured_extraction_implementation: str = "mock",
    structured_extraction_state: str = NOT_IMPLEMENTED,
    skill_normalization_implementation: str = "mock",
    skill_normalization_state: str = NOT_IMPLEMENTED,
    profile_builder_implementation: str = "mock",
    profile_builder_state: str = NOT_IMPLEMENTED,
    knowledge_graph_implementation: str = "mock",
    knowledge_graph_state: str = NOT_IMPLEMENTED,
    graph_rag_implementation: str = "mock",
    graph_rag_state: str = NOT_IMPLEMENTED,
) -> list[dict[str, str]]:
    return [
        {"name": "document_repository", "implementation": "memory", "state": "available"},
        {"name": "ocr", "implementation": "paddleocr", "state": "available"},
        {"name": "data_governance", "implementation": "filesystem", "state": "available"},
        {"name": "data_governance_rag", "implementation": "lexical_chunk_retrieval", "state": "available"},
        {
            "name": "structured_extraction",
            "implementation": structured_extraction_implementation,
            "state": structured_extraction_state,
        },
        {
            "name": "skill_normalization",
            "implementation": skill_normalization_implementation,
            "state": skill_normalization_state,
        },
        {
            "name": "profile_builder",
            "implementation": profile_builder_implementation,
            "state": profile_builder_state,
        },
        {"name": "document_rag", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "knowledge_graph", "implementation": knowledge_graph_implementation, "state": knowledge_graph_state},
        {"name": "graph_rag", "implementation": graph_rag_implementation, "state": graph_rag_state},
        {"name": "position_evolution", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "matching", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "report_generation", "implementation": "mock", "state": NOT_IMPLEMENTED},
    ]
