"""Mocks that expose future seams without producing fake intelligence."""

from __future__ import annotations

from typing import Any

from backend.app.domain.entities import KnowledgeGraphSnapshot, MatchAssessment, Profile, ProfileType, SourceDocument


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
        return _mock(
            "Profile construction is reserved for structured extraction and normalization adapters.",
            attributes={"skills": [], "capabilities": [], "experience": [], "education": None},
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


def capability_catalog() -> list[dict[str, str]]:
    return [
        {"name": "document_repository", "implementation": "memory", "state": "available"},
        {"name": "structured_extraction", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "skill_normalization", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "profile_builder", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "document_rag", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "knowledge_graph", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "graph_rag", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "position_evolution", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "matching", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "report_generation", "implementation": "mock", "state": NOT_IMPLEMENTED},
    ]
