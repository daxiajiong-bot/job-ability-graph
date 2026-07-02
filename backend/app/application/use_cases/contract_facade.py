"""Synchronous use cases for the v3 formal contract."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from backend.app.domain.entities import (
    DocumentType,
    GeneratedReport,
    KnowledgeGraphSnapshot,
    MatchAssessment,
    Profile,
    ProfileType,
    SourceDocument,
)
from backend.app.domain.errors import ResourceConflictError


class ContractFacade:
    """Coordinates resource lifecycle and delegates all intelligence to ports."""

    def __init__(
        self,
        repository: Any,
        extractor: Any,
        normalizer: Any,
        profile_builder: Any,
        document_retriever: Any,
        graph_builder: Any,
        graph_retriever: Any,
        evolution: Any,
        matcher: Any,
        report_generator: Any,
        ocr: Any,
        data_governance: Any,
        capabilities: list[dict[str, str]],
        profile_artifact_store: Any | None = None,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.normalizer = normalizer
        self.profile_builder = profile_builder
        self.document_retriever = document_retriever
        self.graph_builder = graph_builder
        self.graph_retriever = graph_retriever
        self.evolution = evolution
        self.matcher = matcher
        self.report_generator = report_generator
        self.ocr = ocr
        self.data_governance = data_governance
        self.profile_artifact_store = profile_artifact_store
        self._capabilities = capabilities

    def capabilities(self) -> dict[str, Any]:
        return {"capabilities": self._capabilities}

    def create_document(
        self,
        document_type: DocumentType,
        text: str,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document = SourceDocument.create(document_type, text, source, metadata)
        return self.repository.add_document(document).public()

    def get_document(self, document_id: str) -> dict[str, Any]:
        return self.repository.get_document(document_id).public()

    def create_document_from_ocr(
        self,
        document_type: DocumentType,
        file_name: str,
        content: bytes,
        content_type: str | None,
        source: dict[str, Any],
        metadata: dict[str, Any],
        lang: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ocr_result = self.ocr.extract_text(
            file_name=file_name,
            content=content,
            content_type=content_type,
            lang=lang,
            options=options,
        )
        ocr_metadata = self._ocr_metadata(ocr_result, file_name, content_type)
        document_metadata = {**metadata, "ocr": ocr_metadata}
        document = SourceDocument.create(document_type, ocr_result["text"], source, document_metadata)
        return {
            "document": self.repository.add_document(document).public(),
            "ocr": ocr_metadata,
        }

    @staticmethod
    def _ocr_metadata(ocr_result: dict[str, Any], file_name: str, content_type: str | None) -> dict[str, Any]:
        return {
            "state": ocr_result["state"],
            "implementation": ocr_result["implementation"],
            "lang": ocr_result["lang"],
            "source_file_name": file_name,
            "source_content_type": content_type,
            "page_count": ocr_result["page_count"],
            "line_count": ocr_result["line_count"],
            "average_confidence": ocr_result["average_confidence"],
            "warnings": ocr_result.get("warnings", []),
        }

    def create_candidate_profile(self, resume_document_id: str) -> dict[str, Any]:
        return self._create_profile(resume_document_id, DocumentType.RESUME, ProfileType.CANDIDATE)

    def create_job_profile(self, jd_document_id: str) -> dict[str, Any]:
        return self._create_profile(jd_document_id, DocumentType.JD, ProfileType.JOB)

    def get_candidate_profile(self, profile_id: str) -> dict[str, Any]:
        return self.repository.get_profile(profile_id, ProfileType.CANDIDATE).public()

    def get_job_profile(self, profile_id: str) -> dict[str, Any]:
        return self.repository.get_profile(profile_id, ProfileType.JOB).public()

    def _create_profile(
        self,
        document_id: str,
        expected_document_type: DocumentType,
        profile_type: ProfileType,
    ) -> dict[str, Any]:
        document = self.repository.get_document(document_id)
        if document.document_type is not expected_document_type:
            raise ResourceConflictError(
                f"document '{document_id}' is '{document.document_type.value}', expected '{expected_document_type.value}'"
            )
        extraction = self.extractor.extract(document)
        normalization = self.normalizer.normalize(extraction)
        result = self.profile_builder.build(profile_type, document, extraction, normalization)
        profile = Profile.create(profile_type, document.id, result)
        if self.profile_artifact_store is not None:
            artifacts = self.profile_artifact_store.write(
                profile=profile,
                document=document,
                extraction=extraction,
                normalization=normalization,
            )
            profile = replace(profile, artifacts=artifacts)
        return self.repository.add_profile(profile).public()

    def retrieve_document_evidence(
        self,
        query: str,
        document_ids: list[str],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        for document_id in document_ids:
            self.repository.get_document(document_id)
        return self.document_retriever.retrieve(query, document_ids, filters)

    def create_knowledge_graph(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]:
        for document_id in document_ids:
            self.repository.get_document(document_id)
        for profile_id in candidate_profile_ids:
            self.repository.get_profile(profile_id, ProfileType.CANDIDATE)
        for profile_id in job_profile_ids:
            self.repository.get_profile(profile_id, ProfileType.JOB)
        result = self.graph_builder.build(document_ids, candidate_profile_ids, job_profile_ids)
        graph = KnowledgeGraphSnapshot.create(document_ids, candidate_profile_ids, job_profile_ids, result)
        return self.repository.add_graph(graph).public()

    def get_knowledge_graph(self, graph_id: str) -> dict[str, Any]:
        return self.repository.get_graph(graph_id).public()

    def retrieve_graph_evidence(
        self,
        graph_id: str,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]:
        graph = self.repository.get_graph(graph_id)
        return self.graph_retriever.retrieve(graph, query, seed_entity_ids, relation_types)

    def discover_positions(self, document_ids: list[str], options: dict[str, Any]) -> dict[str, Any]:
        for document_id in document_ids:
            self.repository.get_document(document_id)
        return self.evolution.discover(document_ids, options)

    def compare_positions(
        self,
        baseline_job_profile_id: str,
        current_job_profile_id: str,
        supporting_document_ids: list[str],
    ) -> dict[str, Any]:
        baseline = self.repository.get_profile(baseline_job_profile_id, ProfileType.JOB)
        current = self.repository.get_profile(current_job_profile_id, ProfileType.JOB)
        for document_id in supporting_document_ids:
            self.repository.get_document(document_id)
        return self.evolution.delta(baseline, current, supporting_document_ids)

    def create_match(
        self,
        candidate_profile_id: str,
        job_profile_id: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = self.repository.get_profile(candidate_profile_id, ProfileType.CANDIDATE)
        job = self.repository.get_profile(job_profile_id, ProfileType.JOB)
        result = self.matcher.assess(candidate, job, options)
        match = MatchAssessment.create(candidate.id, job.id, result)
        return self.repository.add_match(match).public()

    def get_match(self, match_id: str) -> dict[str, Any]:
        return self.repository.get_match(match_id).public()

    def create_report(self, match_id: str, language: str) -> dict[str, Any]:
        match = self.repository.get_match(match_id)
        result = self.report_generator.generate(match, language)
        report = GeneratedReport.create(match_id, language, result)
        return self.repository.add_report(report).public()

    def register_governance_file(
        self,
        document_type: DocumentType,
        content: bytes,
        file_name: str,
        mime_type: str | None,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self.data_governance.register_upload(
            document_type=document_type.value,
            content=content,
            file_name=file_name,
            mime_type=mime_type,
            source=source,
            metadata=metadata,
        )

    def register_governance_path(
        self,
        document_type: DocumentType,
        path: str,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self.data_governance.register_path(
            document_type=document_type.value,
            path=path,
            source=source,
            metadata=metadata,
        )

    def process_governance_document(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.data_governance.process_document(doc_id, version)

    def get_governance_document(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.data_governance.get_document(doc_id, version)

    def get_governance_lineage(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.data_governance.lineage(doc_id, version)

    def search_governance_rag(self, query: str, doc_ids: list[str], top_k: int) -> dict[str, Any]:
        return self.data_governance.retrieve(query, doc_ids or None, top_k)

    def answer_governance_rag(self, query: str, doc_ids: list[str], top_k: int) -> dict[str, Any]:
        return self.data_governance.answer(query, doc_ids or None, top_k)
