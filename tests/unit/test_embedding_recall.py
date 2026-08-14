"""Unit tests for Qwen3-embedding hybrid recall in auto-match."""

from __future__ import annotations

import numpy as np

from tests.unit.test_auto_match import (
    FakeMatcher,
    _add_document,
    _build_facade,
    _repo,
)


class FakeEmbeddingService:
    """Deterministic embedding service stub."""

    def __init__(self, hits: list[dict] | None = None, fail: bool = False):
        self.hits = hits or []
        self.fail = fail
        self.calls = 0

    def encode_texts(self, texts, is_jd):
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return np.zeros((len(texts), 4), dtype=np.float32)

    def search_index(self, query_vector, index_vectors, index_ids, top_k, exclude_ids=None):
        return self.hits


class FakeVectorIndex:
    size = 3
    ids = ["vdoc-1", "vdoc-2", "vdoc-3"]
    vectors = np.zeros((3, 4), dtype=np.float32)


def test_auto_match_hybrid_recall_merges_embedding_and_sql() -> None:
    """Embedding hits (even with zero skill overlap) join the candidate pool."""
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        sql_jd = _add_document(
            repository, "jd", metadata={"skills": ["Python", "Docker"], "title": "SQL命中"}
        )
        # Semantic-only hit: no skill overlap, but embedding recalls it
        emb_jd = _add_document(
            repository, "jd", metadata={"skills": ["Java"], "title": "语义命中"}
        )
        embedding = FakeEmbeddingService(
            hits=[{"document_id": emb_jd, "similarity": 0.85}]
        )
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 50))
        facade.embedding_service = embedding
        facade.vector_index = FakeVectorIndex()

        result = facade.auto_match(resume_id, top_n=5, user_id="user-1")

        assert result["meta"]["recall"] == "hybrid"
        ids = [r["document"]["document_id"] for r in result["recommendations"]]
        assert sql_jd in ids
        assert emb_jd in ids
        # embedding was actually invoked
        assert embedding.calls == 1


def test_auto_match_embedding_failure_falls_back_to_sql() -> None:
    with _repo() as repository:
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        sql_jd = _add_document(
            repository, "jd", metadata={"skills": ["Python"], "title": "SQL命中"}
        )
        embedding = FakeEmbeddingService(fail=True)
        facade = _build_facade(repository, FakeMatcher(score_fn=lambda m, j: 50))
        facade.embedding_service = embedding
        facade.vector_index = FakeVectorIndex()

        result = facade.auto_match(resume_id, top_n=5, user_id="user-1")

        assert result["meta"]["recall"] == "sql"
        ids = [r["document"]["document_id"] for r in result["recommendations"]]
        assert ids == [sql_jd]


def test_auto_match_embedding_not_used_for_jd_to_resume() -> None:
    """Only the JD vector index exists; JD→resume skips embedding recall."""
    with _repo() as repository:
        jd_id = _add_document(
            repository, "jd", metadata={"skills": ["Python"], "title": "JD输入"}
        )
        resume_id = _add_document(
            repository, "resume", metadata={"skills": ["Python"]}, user_id="user-1"
        )
        embedding = FakeEmbeddingService(
            hits=[{"document_id": "anything", "similarity": 0.9}]
        )
        facade = _build_facade(repository, FakeMatcher())
        facade.embedding_service = embedding
        facade.vector_index = FakeVectorIndex()

        result = facade.auto_match(jd_id, top_n=5, user_id="user-1")

        assert result["meta"]["direction"] == "jd_to_resume"
        assert embedding.calls == 0
        ids = [r["document"]["document_id"] for r in result["recommendations"]]
        assert ids == [resume_id]
