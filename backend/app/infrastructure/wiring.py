"""Composition root for v3 adapters."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Any

from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.data_governance import DataGovernanceService
from backend.app.infrastructure.memory.repositories import InMemoryResourceRepository
from backend.app.infrastructure.mocks.adapters import (
    MockDocumentRetriever,
    MockGraphRetriever,
    MockKnowledgeGraphBuilder,
    MockLearningAdvisor,
    MockMatcher,
    MockPositionEvolution,
    MockProfileBuilder,
    MockReportGenerator,
    MockSkillNormalizer,
    MockStructuredExtractor,
    SQLiteKnowledgeGraphBuilder,
    capability_catalog,
)
from backend.app.infrastructure.ocr import PaddleOcrAdapter
from backend.app.infrastructure.files import ProfileArtifactStore
from backend.app.infrastructure.llm import (
    LLMLearningAdvisor,
    LLMMatcher,
    LLMProfileBuilder,
    LLMReportGenerator,
    LLMSettings,
    LightweightSkillNormalizer,
    OllamaStructuredExtractor,
)


@dataclass(frozen=True)
class ApplicationContainer:
    repository: Any  # InMemoryResourceRepository or SQLiteResourceRepository
    data_governance: DataGovernanceService
    facade: ContractFacade


def build_container(
    ocr: Any | None = None,
    llm_chat_client: Any | None = None,
    data_governance_root: str | None = None,
    profile_artifact_root: str | None = None,
) -> ApplicationContainer:
    max_upload_mb = int(getenv("OCR_MAX_UPLOAD_MB", "20"))
    ocr_adapter = ocr or PaddleOcrAdapter(
        default_lang=getenv("OCR_DEFAULT_LANG", "ch"),
        device=getenv("OCR_DEVICE", "cpu"),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
    )

    # ── Repository: SQLite (persistent) or in-memory (volatile) ──
    db_backend = getenv("DB_BACKEND", "sqlite").strip().lower()
    if db_backend == "sqlite":
        from backend.app.infrastructure.sqlite import DatabaseManager, SQLiteResourceRepository

        db_path = getenv("DB_PATH", str(Path(data_governance_root or getenv("DATA_GOVERNANCE_ROOT", "data")) / "app.db"))
        db_manager = DatabaseManager(db_path)
        repository = SQLiteResourceRepository(db_manager)
    elif db_backend == "memory":
        repository = InMemoryResourceRepository()
    else:
        raise ValueError("DB_BACKEND must be either 'sqlite' or 'memory'")
    extractor: Any = MockStructuredExtractor()
    normalizer: Any = MockSkillNormalizer()
    profile_builder: Any = MockProfileBuilder()
    graph_builder: Any = MockKnowledgeGraphBuilder()
    graph_retriever: Any = MockGraphRetriever()
    capability_options: dict[str, str] = {}

    matcher: Any = MockMatcher()
    report_generator: Any = MockReportGenerator()
    learning_advisor: Any = MockLearningAdvisor()

    llm_settings = LLMSettings.from_env()
    if llm_settings.backend == "ollama":
        extractor = OllamaStructuredExtractor(llm_settings, chat_client=llm_chat_client)
        normalizer = LightweightSkillNormalizer()
        profile_builder = LLMProfileBuilder()
        matcher = LLMMatcher(llm_settings, chat_client=llm_chat_client)
        report_generator = LLMReportGenerator(llm_settings, chat_client=llm_chat_client)
        learning_advisor = LLMLearningAdvisor(llm_settings, chat_client=llm_chat_client)
        capability_options.update(
            structured_extraction_implementation="ollama",
            structured_extraction_state="available",
            skill_normalization_implementation="lightweight",
            skill_normalization_state="available",
            profile_builder_implementation="llm_profile_builder",
            profile_builder_state="available",
            matching_implementation="llm_matcher",
            matching_state="available",
            report_generation_implementation="llm_report_generator",
            report_generation_state="available",
        )
    elif llm_settings.backend != "mock":
        raise ValueError("LLM_BACKEND must be either 'mock' or 'ollama'")

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
        capability_options.update(
            knowledge_graph_implementation="neo4j",
            knowledge_graph_state="available",
            graph_rag_implementation="neo4j",
            graph_rag_state="available",
        )
    elif graph_backend != "mock":
        raise ValueError("GRAPH_BACKEND must be either 'mock' or 'neo4j'")

    governance_root = data_governance_root or getenv("DATA_GOVERNANCE_ROOT", "data")
    if db_backend == "sqlite":
        graph_builder = SQLiteKnowledgeGraphBuilder(repository, data_root=governance_root)
    data_governance = DataGovernanceService(
        root=governance_root,
        llm_chat_client=llm_chat_client,
    )
    profile_artifacts = ProfileArtifactStore(
        profile_artifact_root or getenv("PROFILE_ARTIFACT_ROOT") or Path(governance_root) / "structured" / "profiles"
    )
    capabilities = capability_catalog(**capability_options)
    facade = ContractFacade(
        repository=repository,
        extractor=extractor,
        normalizer=normalizer,
        profile_builder=profile_builder,
        document_retriever=MockDocumentRetriever(),
        graph_builder=graph_builder,
        graph_retriever=graph_retriever,
        evolution=MockPositionEvolution(),
        matcher=matcher,
        report_generator=report_generator,
        learning_advisor=learning_advisor,
        ocr=ocr_adapter,
        data_governance=data_governance,
        capabilities=capabilities,
        profile_artifact_store=profile_artifacts,
    )
    return ApplicationContainer(repository=repository, data_governance=data_governance, facade=facade)
