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
        ocr=ocr_adapter,
        capabilities=capability_catalog(),
    )
    return ApplicationContainer(repository=repository, facade=facade)
