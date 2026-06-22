"""Ports for future implementations; v3 supplies explicit mock adapters only."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from backend.app.domain.entities import (
    DocumentType,
    GeneratedReport,
    KnowledgeGraphSnapshot,
    MatchAssessment,
    Profile,
    ProfileType,
    SourceDocument,
)


class DocumentRepository(Protocol):
    def add_document(self, document: SourceDocument) -> SourceDocument: ...
    def get_document(self, document_id: str) -> SourceDocument: ...


class ProfileRepository(Protocol):
    def add_profile(self, profile: Profile) -> Profile: ...
    def get_profile(self, profile_id: str, expected_type: Optional[ProfileType] = None) -> Profile: ...


class KnowledgeGraphRepository(Protocol):
    def add_graph(self, graph: KnowledgeGraphSnapshot) -> KnowledgeGraphSnapshot: ...
    def get_graph(self, graph_id: str) -> KnowledgeGraphSnapshot: ...


class MatchRepository(Protocol):
    def add_match(self, match: MatchAssessment) -> MatchAssessment: ...
    def get_match(self, match_id: str) -> MatchAssessment: ...


class ReportRepository(Protocol):
    def add_report(self, report: GeneratedReport) -> GeneratedReport: ...


class StructuredExtractionPort(Protocol):
    def extract(self, document: SourceDocument) -> dict[str, Any]: ...


class SkillNormalizationPort(Protocol):
    def normalize(self, extraction: dict[str, Any]) -> dict[str, Any]: ...


class ProfileBuilderPort(Protocol):
    def build(
        self,
        profile_type: ProfileType,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]: ...


class DocumentRetrievalPort(Protocol):
    def retrieve(self, query: str, document_ids: list[str], filters: dict[str, Any]) -> dict[str, Any]: ...


class KnowledgeGraphPort(Protocol):
    def build(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]: ...


class GraphRetrievalPort(Protocol):
    def retrieve(
        self,
        graph: KnowledgeGraphSnapshot,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]: ...


class PositionEvolutionPort(Protocol):
    def discover(self, document_ids: list[str], options: dict[str, Any]) -> dict[str, Any]: ...
    def delta(
        self,
        baseline: Profile,
        current: Profile,
        supporting_document_ids: list[str],
    ) -> dict[str, Any]: ...


class MatchingPort(Protocol):
    def assess(
        self,
        candidate: Profile,
        job: Profile,
        options: dict[str, Any],
    ) -> dict[str, Any]: ...


class ReportGenerationPort(Protocol):
    def generate(self, match: MatchAssessment, language: str) -> dict[str, Any]: ...
