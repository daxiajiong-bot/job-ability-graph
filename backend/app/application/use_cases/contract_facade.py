"""Synchronous use cases for the v3 formal contract."""

from __future__ import annotations

import json
import logging
import re
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
    utc_now,
)

logger = logging.getLogger(__name__)
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
        embedding_service: Any | None = None,
        vector_index: Any | None = None,
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
        self.embedding_service = embedding_service
        self.vector_index = vector_index
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

    def auto_match(
        self,
        document_id: str,
        top_n: int = 5,
        user_id: str | None = None,
        filters: dict[str, Any] | None = None,
        max_per_company: int = 2,
    ) -> dict[str, Any]:
        """Auto-match: recommend the best matching documents for a resume or JD.

        Flow:
        1. Get input document, determine direction (resume → search JDs, JD → search resumes)
        2. Extract skills from the input document (metadata or text fallback)
        3. Build a candidate pool from system + current user documents by skill overlap
           (pool is a superset of ``top_n`` so re-ranking is meaningful)
        4. Apply optional filters (location / industry / company / salary / years)
        5. Score each candidate with the configured matcher
        6. Deduplicate per company, sort, return the top-N recommendations
        """
        filters = dict(filters or {})
        warnings: list[str] = []

        # Serve a previously generated recommendation for the same parameters
        # instead of re-running LLM matching (cache key = user + input doc +
        # top_n + normalized filters + max_per_company).
        cache_user = user_id or "anonymous"
        cache_key_filters = _normalize_filters(filters)
        get_cached = getattr(self.repository, "get_recommendation", None)
        if get_cached is not None:
            cached = get_cached(cache_user, document_id, top_n, cache_key_filters, max_per_company)
            if cached is not None:
                result = cached["result"]
                result["meta"] = {
                    **(result.get("meta") or {}),
                    "cached": True,
                    "cached_at": cached["created_at"],
                }
                return result

        # 1. Get input document
        input_doc = self.repository.get_document(document_id)
        doc_type = input_doc.document_type.value if hasattr(input_doc.document_type, "value") else input_doc.document_type

        # Determine search direction
        if doc_type == "resume":
            target_type = "jd"
            profile_type = ProfileType.CANDIDATE
            target_profile_type = ProfileType.JOB
            direction = "resume_to_jd"
        elif doc_type == "jd":
            target_type = "resume"
            profile_type = ProfileType.JOB
            target_profile_type = ProfileType.CANDIDATE
            direction = "jd_to_resume"
        else:
            raise ValueError(f"Unsupported document type for auto-match: {doc_type}")

        # 2. Extract skills from input document metadata (or text fallback)
        skills = []
        if hasattr(input_doc, "metadata") and input_doc.metadata:
            meta = input_doc.metadata if isinstance(input_doc.metadata, dict) else {}
            skills = list(meta.get("skills", []))
        if not skills:
            text = input_doc.text or ""
            lines = text.splitlines()
            for line in lines:
                if any(kw in line for kw in ("技能", "技术栈", "任职要求", "岗位要求")):
                    skills.extend(re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}|[一-鿿]{2,8}", line))
            skills = list(dict.fromkeys(skills))[:20]

        # 3. Build candidate pool (hybrid: Qwen3-embedding semantic recall +
        #    SQL skill-overlap recall; embedding hits rank first, dedup by id)
        pool_size = min(max(top_n * 8, 40), 120)
        recall = "sql"
        candidates: list[dict[str, Any]] = []

        embedding_hits = self._embedding_recall(
            input_doc, target_type, exclude_doc_id=document_id, top_k=pool_size
        )
        if embedding_hits:
            recall = "hybrid"
            candidates.extend(embedding_hits)

        search_fn = getattr(self.repository, "search_documents_for_recommendation", None)
        use_recommendation_search = search_fn is not None
        if search_fn is None:
            search_fn = getattr(self.repository, "search_documents_by_skills", None)
        if search_fn is None:
            return {
                "input_document": input_doc.public(),
                "input_profile": None,
                "recommendations": [],
                "message": "当前存储后端不支持智能推荐检索",
            }

        search_kwargs: dict[str, Any] = {}
        if use_recommendation_search:
            search_kwargs["filters"] = filters
            # Resume → JD recommendations must also consider JDs posted by HR users
            if target_type == "jd":
                search_kwargs["include_hr_documents"] = True

        sql_candidates = search_fn(
            skills=skills,
            document_type=target_type,
            user_id=user_id or "system",
            exclude_doc_id=document_id,
            limit=pool_size,
            **search_kwargs,
        )
        if sql_candidates:
            if not candidates:
                recall = "sql"
            else:
                recall = "hybrid"
            candidates.extend(sql_candidates)

        # Deduplicate by document id (embedding hits already first)
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for candidate in candidates:
            did = candidate["document"]["document_id"]
            if did in seen:
                continue
            seen.add(did)
            deduped.append(candidate)
        candidates = deduped

        # 4. Apply numeric filters (salary / years) in Python
        candidates = self._apply_numeric_filters(candidates, target_type, filters)

        if not candidates:
            return {
                "input_document": input_doc.public(),
                "input_profile": None,
                "recommendations": [],
                "message": "未找到符合条件的匹配文档",
            }

        # Ensure the input document has a profile (local heuristic, no LLM call)
        input_profile = None
        try:
            input_profile = self._ensure_profile(document_id, profile_type, prefer_heuristic=True)
        except Exception as exc:
            warnings.append(f"输入文档画像生成失败: {exc}")

        # 5. Score candidates (parallel: profile ensure + LLM matching can be slow)
        recommendations: list[dict[str, Any]] = []
        candidate_doc_ids = [c["document"]["document_id"] for c in candidates]
        existing_profiles = self.repository.get_profiles_by_document_ids(
            candidate_doc_ids, target_profile_type.value
        )

        profile_ids: dict[str, str] = {}
        for doc_id in candidate_doc_ids:
            if doc_id in existing_profiles:
                pid = _profile_id(existing_profiles[doc_id])
                if pid:
                    profile_ids[doc_id] = pid

        # Ensure profiles for candidates that do not have one yet (parallel)
        missing_ids = [doc_id for doc_id in candidate_doc_ids if doc_id not in profile_ids]
        if missing_ids:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            workers = min(6, len(missing_ids))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._ensure_candidate_profile, doc_id, target_profile_type): doc_id
                    for doc_id in missing_ids
                }
                for future in as_completed(futures):
                    doc_id = futures[future]
                    try:
                        pid = future.result()
                    except Exception:
                        continue
                    if pid:
                        profile_ids[doc_id] = pid

        # Run matching (parallel). Only the top overlap candidates are scored by
        # the LLM matcher; the rest fall back to overlap-based local matches so
        # that a large pool stays fast when Ollama is slow.
        scorable = [
            (candidate, profile_ids[candidate["document"]["document_id"]])
            for candidate in candidates
            if candidate["document"]["document_id"] in profile_ids
        ]
        scorable.sort(key=lambda pair: pair[0].get("match_count", 0), reverse=True)
        llm_count = min(max(top_n * 2, 4), 9, len(scorable))
        llm_scored = scorable[:llm_count]
        fallback_scored = scorable[llm_count:]

        def _score_candidate(candidate: dict[str, Any], cand_profile_id: str) -> dict[str, Any]:
            cand_doc = candidate["document"]
            match_data: dict[str, Any]
            if input_profile is not None:
                try:
                    options = {"include_document_evidence": False, "include_graph_evidence": False}
                    input_profile_id = _profile_id(input_profile)
                    result = self.matcher.assess(
                        self.repository.get_profile(input_profile_id, profile_type),
                        self.repository.get_profile(cand_profile_id, target_profile_type),
                        options,
                    )
                    match = MatchAssessment.create(input_profile_id, cand_profile_id, result)
                    match_data = self.repository.add_match(match).public()
                except Exception as exc:
                    match_data = {
                        "score": None,
                        "decision": "error",
                        "summary": f"匹配失败: {exc}",
                        "details": {},
                    }
            else:
                # Input profile unavailable → overlap-based local fallback
                match_data = _overlap_fallback_match(cand_doc, skills)

            details = match_data.get("details") or {}
            matched_skills = list(details.get("matched_skills", []))
            missing_skills = list(details.get("missing_skills", []))
            overlap = int(candidate.get("match_count", 0) or 0)

            return {
                "document": cand_doc,
                "profile": existing_profiles.get(cand_doc["document_id"])
                or {"profile_id": cand_profile_id},
                "match": match_data,
                "skill_overlap": overlap,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "reasons": _build_recommendation_reasons(cand_doc, overlap, matched_skills, missing_skills, filters),
            }

        if llm_scored:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            workers = min(6, len(llm_scored))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_score_candidate, candidate, pid) for candidate, pid in llm_scored]
                for future in as_completed(futures):
                    try:
                        recommendations.append(future.result())
                    except Exception:
                        continue

        # Remaining candidates: fast overlap-based fallback (no LLM call)
        for candidate, cand_profile_id in fallback_scored:
            cand_doc = candidate["document"]
            match_data = _overlap_fallback_match(cand_doc, skills)
            details = match_data.get("details") or {}
            matched_skills = list(details.get("matched_skills", []))
            missing_skills = list(details.get("missing_skills", []))
            overlap = int(candidate.get("match_count", 0) or 0)
            recommendations.append({
                "document": cand_doc,
                "profile": existing_profiles.get(cand_doc["document_id"])
                or {"profile_id": cand_profile_id},
                "match": match_data,
                "skill_overlap": overlap,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "reasons": _build_recommendation_reasons(cand_doc, overlap, matched_skills, missing_skills, filters),
            })

        # 6. Deduplicate per company, then sort & truncate to top_n
        recommendations = _dedupe_by_company(recommendations, max_per_company)
        recommendations.sort(key=_recommendation_sort_key, reverse=True)
        recommendations = recommendations[:top_n]

        has_scores = any((r.get("match") or {}).get("score") is not None for r in recommendations)
        result = {
            "input_document": input_doc.public(),
            "input_profile": input_profile,
            "recommendations": recommendations,
            "meta": {
                "direction": direction,
                "pool_size": len(candidates),
                "top_n": top_n,
                "llm_scored": llm_count,
                "recall": recall,
                "filters": filters or None,
                "max_per_company": max_per_company,
                "ranking": "matcher_score" if has_scores else "skill_overlap",
                "warnings": warnings,
            },
        }

        # Persist the generated recommendation so repeat requests hit the cache
        save = getattr(self.repository, "save_recommendation", None)
        if save is not None:
            try:
                save(cache_user, document_id, direction, top_n, cache_key_filters, max_per_company, result)
            except Exception as exc:
                warnings.append(f"推荐结果保存失败: {exc}")

        result["meta"] = {
            **result["meta"],
            "cached": False,
            "cached_at": utc_now(),
        }
        return result

    def _embedding_recall(
        self,
        input_doc: SourceDocument,
        target_type: str,
        exclude_doc_id: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Semantic recall via the Qwen3-Embedding-4B vector index.

        Currently indexes JD documents, so it only augments the resume→JD
        direction. Any failure falls back silently to keyword recall.
        """
        if (
            self.embedding_service is None
            or self.vector_index is None
            or self.vector_index.size == 0
            or target_type != "jd"
        ):
            return []
        try:
            title = getattr(input_doc, "title", None) or ""
            text = f"{title}\n{input_doc.text or ''}".strip()
            if not text:
                return []
            query_vec = self.embedding_service.encode_texts([text], is_jd=False)
            hits = self.embedding_service.search_index(
                query_vec[0],
                self.vector_index.vectors,
                self.vector_index.ids,
                top_k=top_k,
                exclude_ids=[exclude_doc_id] if exclude_doc_id else None,
            )
            if not hits:
                return []
            docs = self.repository.get_documents_by_ids([h["document_id"] for h in hits])
            results: list[dict[str, Any]] = []
            for hit in hits:
                doc = docs.get(hit["document_id"])
                if doc is None:
                    continue
                results.append({
                    "document": doc,
                    "match_count": 0,
                    "similarity": hit["similarity"],
                })
            return results
        except Exception as exc:
            logger.warning("embedding recall skipped: %s", exc)
            return []

    def _apply_numeric_filters(
        self,
        candidates: list[dict[str, Any]],
        target_type: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Post-filter candidates by numeric salary / experience constraints."""
        if not candidates or not filters:
            return candidates

        salary_min = filters.get("salary_min")
        salary_max = filters.get("salary_max")
        years_min = filters.get("years_min")

        if salary_min is None and salary_max is None and years_min is None:
            return candidates

        filtered: list[dict[str, Any]] = []
        for candidate in candidates:
            doc = candidate["document"]
            keep = True

            # Salary constraints only make sense for JD targets (resumes rarely carry salary)
            if target_type == "jd" and (salary_min is not None or salary_max is not None):
                lo, hi = _parse_salary_range(doc.get("salary_range"))
                if lo is None and hi is None:
                    # unparseable salary → keep (cannot verify, do not over-filter)
                    pass
                else:
                    if salary_min is not None and (hi is None or hi < float(salary_min)):
                        keep = False
                    if keep and salary_max is not None and (lo is None or lo > float(salary_max)):
                        keep = False

            if keep and years_min is not None:
                years = _parse_experience_years(doc.get("experience"))
                if years is not None and years < float(years_min):
                    keep = False

            if keep:
                filtered.append(candidate)

        return filtered

    def _ensure_profile(
        self,
        document_id: str,
        profile_type: ProfileType,
        prefer_heuristic: bool = False,
    ) -> dict[str, Any]:
        """Get existing profile or create a new one synchronously.

        With ``prefer_heuristic=True`` the profile is built locally from the
        document text without any LLM call — used for recommendation candidates
        so a large candidate pool stays fast even when Ollama is slow.
        """
        # Try to get existing profile
        existing = self.repository.get_profile_by_document(document_id, profile_type.value)
        if existing:
            return existing

        # Create new profile
        document = self.repository.get_document(document_id)
        if prefer_heuristic:
            extraction = _heuristic_extraction()
            normalization = {
                "state": "not_implemented",
                "implementation": "heuristic",
                "skills": [],
                "warnings": [],
            }
        else:
            extraction = self.extractor.extract(document)
            normalization = self.normalizer.normalize(extraction)
        result = self.profile_builder.build(profile_type, document, extraction, normalization)
        profile = Profile.create(profile_type, document.id, result)
        self.repository.add_profile(profile)
        return profile.public()

    def _ensure_candidate_profile(self, document_id: str, profile_type: ProfileType) -> str:
        """Ensure a profile exists for a candidate document and return its id.

        Candidates are built with the fast local heuristic profile so that a
        large pool does not trigger one LLM extraction per document.
        Designed to run inside a thread pool (repository is thread-safe via
        thread-local SQLite connections).
        """
        profile = self._ensure_profile(document_id, profile_type, prefer_heuristic=True)
        return _profile_id(profile)

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


# ── Auto-match helpers ─────────────────────────────────


def _profile_id(profile: dict[str, Any]) -> str:
    """Unify the two public profile representations.

    ``Profile.public()`` exposes ``id`` while ``ProfileRow.to_public()``
    exposes both ``id`` and ``profile_id``; accept either.
    """
    return profile.get("profile_id") or profile.get("id")


def _heuristic_extraction() -> dict[str, Any]:
    """Extraction stub that forces profile builders into their local heuristic path."""
    return {
        "state": "not_implemented",
        "implementation": "heuristic",
        "reason": "Heuristic profile built locally for recommendation candidates (no LLM call).",
        "fields": {},
        "evidence": [],
        "warnings": ["Profile built with local heuristic extraction for speed."],
    }


def _normalize_filters(filters: dict[str, Any] | None) -> str | None:
    """Canonical cache key for filter dicts (key order independent)."""
    if not filters:
        return None
    return json.dumps(filters, sort_keys=True, ensure_ascii=True)


def _parse_salary_range(value: Any) -> tuple[float | None, float | None]:
    """Best-effort parse of a free-text salary range into (min_k, max_k) per month.

    Supports forms like ``15k-25k``, ``15-25K``, ``8~12k``, ``15000-25000元``,
    ``1.5-2万/月``. Returns ``(None, None)`` when unparseable.
    """
    if not value:
        return None, None
    text = str(value).strip()
    if "万" in text:
        unit = 10.0  # 1 万 = 10k
    elif "k" in text.casefold():
        unit = 1.0  # already in k
    else:
        unit = 0.001  # assume yuan per month → k
    text = re.sub(r"[~～至到]", "-", text)
    parts = re.findall(r"\d+(?:\.\d+)?", text)
    if not parts:
        return None, None
    nums = [float(part) * unit for part in parts]
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums), max(nums)


def _parse_experience_years(value: Any) -> float | None:
    """Extract years from free text like ``3年以上``, ``5年`` or ``1-3年``.

    Returns the minimum bound when a range is present.
    """
    if not value:
        return None
    text = str(value)
    if "年" not in text and "years" not in text.casefold():
        return None
    parts = re.findall(r"\d+(?:\.\d+)?", text)
    if not parts:
        return None
    return min(float(part) for part in parts)


def _build_recommendation_reasons(
    document: dict[str, Any],
    overlap: int,
    matched_skills: list[str],
    missing_skills: list[str],
    filters: dict[str, Any],
) -> list[str]:
    """Human-readable reasons explaining why a document was recommended."""
    reasons: list[str] = []
    if overlap > 0:
        reasons.append(f"技能重叠 {overlap} 项")
    if matched_skills:
        reasons.append(f"已掌握：{'、'.join(matched_skills[:4])}")
    if missing_skills:
        reasons.append(f"待补强：{'、'.join(missing_skills[:4])}")
    location = document.get("location")
    if location and filters.get("location"):
        reasons.append(f"地点符合：{location}")
    company = document.get("company_name")
    if company and filters.get("company_name"):
        reasons.append(f"公司符合：{company}")
    return reasons


def _dedupe_by_company(items: list[dict[str, Any]], max_per_company: int) -> list[dict[str, Any]]:
    """Keep at most ``max_per_company`` items per company (0 = unlimited)."""
    if max_per_company <= 0:
        return items
    counts: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for item in items:
        company = (item.get("document") or {}).get("company_name") or ""
        key = str(company).strip().casefold()
        if not key:
            result.append(item)
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= max_per_company:
            result.append(item)
    return result


def _recommendation_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """Sort key: matcher score first when available, otherwise skill overlap.

    Mock mode produces ``score=None`` matches; ranking by overlap keeps the
    recommendation list meaningful without an LLM.
    """
    match = item.get("match") or {}
    score = match.get("score")
    overlap = float(item.get("skill_overlap", 0) or 0)
    title = (item.get("document") or {}).get("title") or ""
    if score is None:
        return (0, overlap, 0.0, title)
    return (1, float(score), overlap, title)


def _overlap_fallback_match(document: dict[str, Any], input_skills: list[str]) -> dict[str, Any]:
    """Local overlap-based match used when the input profile could not be built."""
    doc_skills = list(document.get("skills", []))
    input_set = {str(s).casefold().strip() for s in input_skills if s}
    doc_set = {str(s).casefold().strip() for s in doc_skills if s}
    matched = [s for s in doc_skills if str(s).casefold().strip() in input_set]
    missing = [s for s in input_skills if str(s).casefold().strip() not in doc_set]
    return {
        "score": None,
        "decision": "not_evaluated",
        "summary": "输入文档画像不可用，已按技能重叠度排序。",
        "details": {
            "matched_skills": matched,
            "missing_skills": missing,
        },
        "warnings": ["输入文档画像生成失败，匹配分数未评估"],
    }
