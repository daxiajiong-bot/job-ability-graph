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
    Task,
    TaskStatus,
)
from backend.app.domain.errors import ResourceConflictError, ResourceNotFoundError


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
        learning_advisor: Any,
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
        self.learning_advisor = learning_advisor
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
        user_id: str | None = None,
    ) -> dict[str, Any]:
        document = SourceDocument.create(document_type, text, source, metadata)
        # Pass user_id to repository if it supports it (SQLite)
        if user_id and hasattr(self.repository, "_db"):
            # The browser can send its first document request immediately
            # after creating the ID, before /users/init has completed.
            if hasattr(self.repository, "ensure_user"):
                self.repository.ensure_user(user_id)
            self.repository.add_document(document, user_id=user_id)
        else:
            self.repository.add_document(document)
        return document.public()

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
        user_id: str | None = None,
    ) -> dict[str, Any]:
        ocr_result = self.ocr.extract_text(
            file_name=file_name,
            content=content,
            content_type=content_type,
            lang=lang,
            options=options,
        )
        ocr_metadata = self._ocr_metadata(ocr_result, file_name, content_type)
        # 只返回 OCR 识别结果，不创建文档
        # 文档将在用户校正确认后由 create_document 接口创建
        return {
            "document": {
                "text": ocr_result["text"],
                "confidence": ocr_result.get("average_confidence"),
                "filename": file_name,
            },
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

    def get_candidate_profiles_by_documents(self, document_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return {document_id: profile_public} for documents that have candidate profiles."""
        result = {}
        for doc_id in document_ids:
            profile = self.repository.get_profile_by_document(doc_id, "candidate")
            if profile is not None:
                result[doc_id] = profile
        return result

    def get_job_profiles_by_documents(self, document_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return {document_id: profile_public} for documents that have job profiles."""
        result = {}
        for doc_id in document_ids:
            profile = self.repository.get_profile_by_document(doc_id, "job")
            if profile is not None:
                result[doc_id] = profile
        return result

    # ── Async task interface ──────────────────────────────

    def start_create_candidate_profile(self, document_id: str) -> Task:
        return self._start_profile_task(document_id, DocumentType.RESUME, "create_candidate_profile")

    def start_create_job_profile(self, document_id: str) -> Task:
        return self._start_profile_task(document_id, DocumentType.JD, "create_job_profile")

    def _start_profile_task(self, document_id: str, expected_type: DocumentType, task_type: str) -> Task:
        document = self.repository.get_document(document_id)
        if document.document_type is not expected_type:
            raise ResourceConflictError(
                f"document '{document_id}' is '{document.document_type.value}', expected '{expected_type.value}'"
            )
        task = Task.create(task_type=task_type, document_id=document_id)
        return self.repository.add_task(task)

    def execute_profile_task(self, task_id: str) -> None:
        """Run profile extraction in background. Called by FastAPI BackgroundTasks."""
        task = self.repository.get_task(task_id)
        self.repository.update_task(task_id, status=TaskStatus.RUNNING)
        try:
            if task.task_type == "create_candidate_profile":
                profile = self._create_profile(task.document_id, DocumentType.RESUME, ProfileType.CANDIDATE)
            else:
                profile = self._create_profile(task.document_id, DocumentType.JD, ProfileType.JOB)
            self.repository.update_task(task_id, status=TaskStatus.SUCCEEDED, profile_id=profile["id"])
        except Exception as exc:
            self.repository.update_task(task_id, status=TaskStatus.FAILED, error=str(exc))

    def get_task(self, task_id: str) -> Task:
        return self.repository.get_task(task_id)

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

    def generate_learning_advice(self, match_id: str) -> dict[str, Any]:
        match = self.repository.get_match(match_id)
        match_data = match.public() if hasattr(match, "public") else {}
        return self.learning_advisor.generate(match_data)

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
        governed_ids = self._ensure_governed_document_ids(doc_ids)
        return self.data_governance.retrieve(query, governed_ids or None, top_k)

    def answer_governance_rag(self, query: str, doc_ids: list[str], top_k: int) -> dict[str, Any]:
        governed_ids = self._ensure_governed_document_ids(doc_ids)
        return self.data_governance.answer(query, governed_ids or None, top_k)

    def _ensure_governed_document_ids(self, document_ids: list[str]) -> list[str]:
        """Bridge ordinary uploaded resources into the evidence-first governance pipeline."""
        if not document_ids:
            return []
        governed_ids: list[str] = []
        for document_id in document_ids:
            try:
                self.data_governance.get_document(document_id)
                governed_ids.append(document_id)
                continue
            except ResourceNotFoundError:
                pass

            source_document = self.repository.get_document(document_id)
            registered = self.data_governance.register_upload(
                document_type=source_document.document_type.value,
                content=source_document.text.encode("utf-8"),
                file_name=f"{document_id}.txt",
                mime_type="text/plain",
                source={"source_system": "resource_repository", "external_id": document_id},
                metadata={"source_document_id": document_id},
            )
            governed_document = registered["document"]
            governed_id = governed_document["doc_id"]
            version = governed_document.get("version")
            self.data_governance.process_document(governed_id, version)
            governed_ids.append(governed_id)
        return governed_ids
