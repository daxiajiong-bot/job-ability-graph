"""Composition root for v3 adapters."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from typing import Any

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
from backend.app.infrastructure.ocr import PaddleOcrAdapter


@dataclass(frozen=True)
class ApplicationContainer:
    repository: InMemoryResourceRepository
    facade: ContractFacade


def build_container(ocr: Any | None = None) -> ApplicationContainer:
    max_upload_mb = int(getenv("OCR_MAX_UPLOAD_MB", "20"))
    ocr_adapter = ocr or PaddleOcrAdapter(
        default_lang=getenv("OCR_DEFAULT_LANG", "ch"),
        device=getenv("OCR_DEVICE", "cpu"),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
    )
    repository = InMemoryResourceRepository()
    graph_builder: Any = MockKnowledgeGraphBuilder()
    graph_retriever: Any = MockGraphRetriever()
    capabilities = capability_catalog()

    graph_backend = getenv("GRAPH_BACKEND", "mock").strip().lower()
    if graph_backend == "neo4j":
        from backend.app.infrastructure.neo4j import (
            Neo4jGraphRetriever,
            Neo4jGraphStore,
            Neo4jKnowledgeGraphBuilder,
            Neo4jSettings,
        )

        neo4j_store = Neo4jGraphStore(Neo4jSettings.from_env())
        graph_builder = Neo4jKnowledgeGraphBuilder(repository, neo4j_store)
        graph_retriever = Neo4jGraphRetriever(neo4j_store)
        capabilities = capability_catalog(
            knowledge_graph_implementation="neo4j",
            knowledge_graph_state="available",
            graph_rag_implementation="neo4j",
            graph_rag_state="available",
        )
    elif graph_backend != "mock":
        raise ValueError("GRAPH_BACKEND must be either 'mock' or 'neo4j'")

    facade = ContractFacade(
        repository=repository,
        extractor=MockStructuredExtractor(),
        normalizer=MockSkillNormalizer(),
        profile_builder=MockProfileBuilder(),
        document_retriever=MockDocumentRetriever(),
        graph_builder=graph_builder,
        graph_retriever=graph_retriever,
        evolution=MockPositionEvolution(),
        matcher=MockMatcher(),
        report_generator=MockReportGenerator(),
        ocr=ocr_adapter,
        capabilities=capabilities,
    )
    return ApplicationContainer(repository=repository, facade=facade)
