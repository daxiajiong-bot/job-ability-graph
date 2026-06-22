"""Composition root: mock adapters are the only implementations wired in v3."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.infrastructure.memory.repositories import InMemoryResourceRepository
from backend.app.infrastructure.mocks.adapters import (
    MockDocumentRetriever,
    MockGraphRetriever,
    MockKnowledgeGraphBuilder,
    MockMatcher,
    MockPositionEvolution,
    MockProfileBuilder,
    MockReportGenerator,
    MockSkillNormalizer,
    MockStructuredExtractor,
    capability_catalog,
)


@dataclass(frozen=True)
class ApplicationContainer:
    repository: InMemoryResourceRepository
    facade: ContractFacade


def build_container() -> ApplicationContainer:
    repository = InMemoryResourceRepository()
    facade = ContractFacade(
        repository=repository,
        extractor=MockStructuredExtractor(),
        normalizer=MockSkillNormalizer(),
        profile_builder=MockProfileBuilder(),
        document_retriever=MockDocumentRetriever(),
        graph_builder=MockKnowledgeGraphBuilder(),
        graph_retriever=MockGraphRetriever(),
        evolution=MockPositionEvolution(),
        matcher=MockMatcher(),
        report_generator=MockReportGenerator(),
        capabilities=capability_catalog(),
    )
    return ApplicationContainer(repository=repository, facade=facade)
