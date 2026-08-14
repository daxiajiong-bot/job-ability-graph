"""Unit tests for the intelligent recommendation (auto-match) flow."""

from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from backend.app.application.use_cases.contract_facade import (
    _dedupe_by_company,
    _parse_experience_years,
    _parse_salary_range,
    ContractFacade,
)
from backend.app.domain.entities import DocumentType, SourceDocument
from backend.app.infrastructure.mocks.adapters import (
    MockDocumentRetriever,
    MockGraphRetriever,
    MockKnowledgeGraphBuilder,
    MockLearningAdvisor,
    MockPositionEvolution,
    MockReportGenerator,
    MockSkillNormalizer,
    MockStructuredExtractor,
)
from backend.app.infrastructure.sqlite.db import DatabaseManager
from backend.app.infrastructure.sqlite.repository import SQLiteResourceRepository

# Workspace-local temp root: sandboxed environments may deny cleanup in the
# system temp directory, so DB scratch dirs live under the test folder.
_TMP_ROOT = Path(__file__).resolve().parent / ".tmp"


@contextmanager
def _repo() -> Iterator[SQLiteResourceRepository]:
    # NOTE: use os-style mkdir (not tempfile.mkdtemp) — under the file sandbox,
    # sqlite3 cannot open databases inside mkdtemp-created directories.
    _TMP_ROOT.mkdir(exist_ok=True)
    tempdir = _TMP_ROOT / f"db_{uuid.uuid4().hex[:10]}"
    tempdir.mkdir()
    manager = DatabaseManager(tempdir / "app.db")
    repository = SQLiteResourceRepository(manager)
    repository.ensure_user("system")
    try:
        yield repository
    finally:
        manager.close()
        shutil.rmtree(str(tempdir), ignore_errors=True)


class SkillsProfileBuilder:
    """Test profile builder that carries the document's metadata skills."""

    def build(self, profile_type, document, extraction, normalization):
        attributes = {"skills": list(document.metadata.get("skills", []))}
        return {
            "state": "available",
            "implementation": "test_profile_builder",
            "attributes": attributes,
            "evidence": [],
            "warnings": [],
        }


class FakeMatcher:
    """Deterministic matcher; scores are optional (None → mock-like behavior)."""

    def __init__(self, score_fn=None):
        self.score_fn = score_fn

    def assess(self, candidate, job, options=None):
        def name(s):
            return s.get("name") if isinstance(s, dict) else str(s)

        cand_names = {name(s) for s in candidate.attributes.get("skills", []) if name(s)}
        job_names = [name(s) for s in job.attributes.get("skills", []) if name(s)]
        matched = [s for s in job_names if s in cand_names]
        missing = [s for s in job_names if s not in cand_names]
        score = None
        if self.score_fn is not None:
            score = self.score_fn(matched, job_names)
        return {
            "state": "available",
            "implementation": "fake_matcher",
            "score": score,
            "decision": "match" if score is not None and score >= 60 else "partial_match",
            "strengths": [],
            "gaps": [],
            "learning_path": [],
            "document_evidence": [],
            "graph_evidence": [],
            "details": {"matched_skills": matched, "missing_skills": missing},
            "summary": "fake summary",
            "warnings": [],
        }


def _build_facade(repository: SQLiteResourceRepository, matcher: FakeMatcher) -> ContractFacade:
    return ContractFacade(
        repository=repository,
        extractor=MockStructuredExtractor(),
        normalizer=MockSkillNormalizer(),
        profile_builder=SkillsProfileBuilder(),
        document_retriever=MockDocumentRetriever(),
        graph_builder=MockKnowledgeGraphBuilder(),
        graph_retriever=MockGraphRetriever(),
        evolution=MockPositionEvolution(),
        matcher=matcher,
        report_generator=MockReportGenerator(),
        learning_advisor=MockLearningAdvisor(),
        ocr=None,
        data_governance=None,
        capabilities=[],
        profile_artifact_store=None,
    )


def _add_document(
    repository: SQLiteResourceRepository,
    document_type: str,
    text: str = "",
    metadata: dict | None = None,
    user_id: str = "system",
    doc_id: str | None = None,
) -> str:
    document = SourceDocument.create(
        DocumentType(document_type),
        text or "这是一份用于测试的文档，不含技能关键词行。",
        {"source_system": "test"},
        metadata or {},
    )
    if doc_id:
        document = replace(document, id=doc_id)
    repository.ensure_user(user_id)
    repository.add_document(document, user_id=user_id)
    return document.id


def test_auto_match_resume_to_jd_returns_system_jds() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python", "Docker"]}, user_id="user-1"
        )
        jd_weak = _add_document(
            repository, "jd", metadata={"skills": ["Java"], "company_name": "甲厂"}
        )
        jd_strong = _add_document(
            repository, "jd", metadata={"skills": ["Python", "Docker", "Kubernetes"], "company_name": "乙厂"}
        )
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: len(m) * 30))

        result = facade.auto_match(resume_id, top_n=5, user_id="user-1")

        assert result["input_profile"] is not None
        # jd_weak (Java only) has zero skill overlap → excluded from the pool
        assert len(result["recommendations"]) == 1
        # Highest matcher score first (2 matched → 60 vs 0 → 0)
        assert result["recommendations"][0]["document"]["document_id"] == jd_strong
        assert result["recommendations"][0]["match"]["score"] == 60
        assert result["recommendations"][0]["skill_overlap"] == 2
        assert result["meta"]["direction"] == "resume_to_jd"
        assert result["meta"]["pool_size"] == 1


def test_auto_match_jd_to_resume_includes_user_resumes() -> None:
    """JD→resume must search the current user's resumes (previously returned empty)."""
    with _repo() as repository:
        jd_id = _add_document(
            repository, "jd", metadata={"skills": ["Python"], "company_name": "招聘方"}
        )
        # Only user resumes exist; the system has no resume documents.
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python", "FastAPI"]}, user_id="user-1"
        )
        facade = _build_facade(repository, FakeMatcher())

        result = facade.auto_match(jd_id, top_n=5, user_id="user-1")

        assert result["meta"]["direction"] == "jd_to_resume"
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["document"]["document_id"] == resume_id


def test_auto_match_resume_to_jd_includes_hr_jds() -> None:
    """Resume→JD recommendations must include JDs posted by HR users.

    Other job seekers' documents stay isolated; only system JDs, the current
    user's JDs and HR-posted JDs form the candidate pool.
    """
    with _repo() as repository:
        hr_uid = "hr-user-1"
        repository.ensure_user(hr_uid)
        repository._db.execute("UPDATE users SET role = 'hr' WHERE user_id = ?", (hr_uid,))
        repository._db.commit()
        # another job seeker (default role) whose JD must NOT leak into the pool
        repository.ensure_user("seeker-2")

        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        hr_jd = _add_document(
            repository,
            "jd",
            metadata={"skills": ["Python", "Docker"], "company_name": "HR招聘公司"},
            user_id=hr_uid,
        )
        _add_document(
            repository,
            "jd",
            metadata={"skills": ["Python"], "company_name": "其他求职者"},
            user_id="seeker-2",
        )
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 60))

        result = facade.auto_match(resume_id, top_n=5, user_id="user-1")

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["document"]["document_id"] == hr_jd
        assert result["recommendations"][0]["document"]["company_name"] == "HR招聘公司"


def test_auto_match_filters_by_location() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python"], "location": "北京"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "location": "上海"})
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 50))

        result = facade.auto_match(
            resume_id, top_n=5, user_id="user-1", filters={"location": "北京"}
        )

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["document"]["location"] == "北京"


def test_auto_match_salary_filter() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python"], "salary_range": "15k-25k"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "salary_range": "8k-10k"})
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 50))

        result = facade.auto_match(
            resume_id, top_n=5, user_id="user-1", filters={"salary_min": 12}
        )

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["document"]["salary_range"] == "15k-25k"


def test_auto_match_deduplicates_per_company() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python"], "company_name": "某科技"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "company_name": "某科技"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "company_name": "某科技"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "company_name": "另一家"})
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 50))

        result = facade.auto_match(resume_id, top_n=10, user_id="user-1", max_per_company=2)

        companies = [r["document"]["company_name"] for r in result["recommendations"]]
        assert companies.count("某科技") <= 2
        assert "另一家" in companies


def test_auto_match_mock_scores_none_ranks_by_overlap() -> None:
    """When the matcher returns no score (mock mode), ranking falls back to overlap."""
    with _repo() as repository:
        resume_id = _add_document(
            repository,
            "resume",
            metadata={"skills": ["Python", "Docker", "Kubernetes", "Redis"]},
            user_id="user-1",
        )
        _add_document(repository, "jd", metadata={"skills": ["Python"]})
        _add_document(repository, "jd", metadata={"skills": ["Python", "Docker", "Kubernetes"]})
        facade = _build_facade(repository, FakeMatcher())  # score_fn=None

        result = facade.auto_match(resume_id, top_n=5, user_id="user-1")

        assert all(r["match"]["score"] is None for r in result["recommendations"])
        # 3-overlap JD ranks above 1-overlap JD
        assert result["recommendations"][0]["skill_overlap"] == 3
        assert result["meta"]["ranking"] == "skill_overlap"


def test_auto_match_reranks_beyond_sql_order() -> None:
    """A larger candidate pool allows the matcher to promote lower-overlap docs.

    Both JDs have the same skill overlap with the resume, so the matcher score
    (driven by an extra distinctive skill) decides the ranking. With the old
    ``limit=top_n`` pool the second JD could be cut before scoring.
    """
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python", "A", "B"], "title": "低分岗位"})
        _add_document(repository, "jd", metadata={"skills": ["Python", "X"], "title": "高分岗位"})

        # X is a distinctive skill the matcher rewards heavily
        def score_fn(matched, job_skills):
            return 95 if "X" in job_skills else 10

        facade = _build_facade(repository, FakeMatcher(score_fn=score_fn))

        result = facade.auto_match(resume_id, top_n=1, user_id="user-1")

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["document"]["title"] == "高分岗位"
        assert result["recommendations"][0]["match"]["score"] == 95


# ── Recommendation caching ─────────────────────────────


class CountingMatcher(FakeMatcher):
    def __init__(self, score_fn=None):
        super().__init__(score_fn=score_fn)
        self.calls = 0

    def assess(self, candidate, job, options=None):
        self.calls += 1
        return super().assess(candidate, job, options)


def test_auto_match_caches_result_and_skips_rematch() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python", "Docker"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python", "Docker", "K8s"]})
        _add_document(repository, "jd", metadata={"skills": ["Python", "FastAPI"]})
        matcher = CountingMatcher(score_fn=lambda m, j: 60)
        facade = _build_facade(repository, matcher)

        first = facade.auto_match(resume_id, top_n=3, user_id="user-1")
        assert first["meta"]["cached"] is False
        scored_once = matcher.calls
        assert scored_once >= 1

        second = facade.auto_match(resume_id, top_n=3, user_id="user-1")
        assert second["meta"]["cached"] is True
        assert second["meta"]["cached_at"] is not None
        # matcher must not run again on a cache hit
        assert matcher.calls == scored_once
        # same recommendations served from cache
        assert second["recommendations"] == first["recommendations"]


def test_auto_match_cache_respects_parameters() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python", "Docker"]})
        matcher = CountingMatcher(score_fn=lambda m, j: 60)
        facade = _build_facade(repository, matcher)

        facade.auto_match(resume_id, top_n=2, user_id="user-1")
        calls_after_top2 = matcher.calls
        assert facade.auto_match(resume_id, top_n=2, user_id="user-1")["meta"]["cached"] is True

        # different top_n → different cache entry → recompute
        r3 = facade.auto_match(resume_id, top_n=3, user_id="user-1")
        assert r3["meta"]["cached"] is False
        assert matcher.calls > calls_after_top2


def test_auto_match_cache_respects_filters() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        _add_document(repository, "jd", metadata={"skills": ["Python"], "location": "北京"})
        _add_document(repository, "jd", metadata={"skills": ["Python"], "location": "上海"})
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 60))

        facade.auto_match(resume_id, top_n=3, user_id="user-1", filters={"location": "北京"})
        assert facade.auto_match(resume_id, top_n=3, user_id="user-1", filters={"location": "北京"})["meta"]["cached"] is True

        # different filter value → separate cache entry
        r_shanghai = facade.auto_match(resume_id, top_n=3, user_id="user-1", filters={"location": "上海"})
        assert r_shanghai["meta"]["cached"] is False
        assert r_shanghai["recommendations"][0]["document"]["location"] == "上海"


# ── Pure helper tests ──────────────────────────────────


def test_parse_salary_range() -> None:
    assert _parse_salary_range("15k-25k") == (15.0, 25.0)
    assert _parse_salary_range("8~12K") == (8.0, 12.0)
    assert _parse_salary_range("15000-25000元") == (15.0, 25.0)
    assert _parse_salary_range("1.5-2万/月") == (15.0, 20.0)
    assert _parse_salary_range("面议") == (None, None)
    assert _parse_salary_range(None) == (None, None)


def test_parse_experience_years() -> None:
    assert _parse_experience_years("3年以上") == 3.0
    assert _parse_experience_years("3-5年") == 3.0
    assert _parse_experience_years("五年") is None
    assert _parse_experience_years(None) is None


def test_dedupe_by_company() -> None:
    items = [
        {"document": {"company_name": "甲"}},
        {"document": {"company_name": "甲"}},
        {"document": {"company_name": "甲"}},
        {"document": {"company_name": "乙"}},
        {"document": {}},
    ]
    result = _dedupe_by_company(items, max_per_company=2)
    companies = [i["document"].get("company_name") for i in result]
    assert companies.count("甲") == 2
    assert companies.count("乙") == 1
    assert companies.count(None) == 1
    # unlimited
    assert len(_dedupe_by_company(items, max_per_company=0)) == 5
