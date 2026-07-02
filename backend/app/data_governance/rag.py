"""Minimal evidence-first RAG over governed chunks."""

from __future__ import annotations

import re
from typing import Any

from backend.app.data_governance.store import DataGovernanceStore


class DataGovernanceRag:
    def __init__(self, store: DataGovernanceStore) -> None:
        self.store = store

    def retrieve(self, query: str, doc_ids: list[str] | None = None, top_k: int = 5) -> dict[str, Any]:
        query = query.strip()
        terms = query_terms(query)
        scored: list[dict[str, Any]] = []
        for chunk in self.store.iter_rag_chunks(doc_ids):
            score = score_chunk(chunk["text"], terms, query)
            skill_hits = [skill for skill in chunk.get("skills", []) if skill.casefold() in query.casefold()]
            score += len(skill_hits) * 5
            if score <= 0:
                continue
            quote, start, end = quote_for(chunk["text"], terms, query)
            scored.append(
                {
                    "doc_id": chunk["doc_id"],
                    "version": chunk["version"],
                    "chunk_id": chunk["chunk_id"],
                    "score": score,
                    "quote": quote,
                    "quote_start_char": chunk["start_char"] + start,
                    "quote_end_char": chunk["start_char"] + end,
                    "raw_path": chunk["raw_path"],
                    "content_hash": chunk["content_hash"],
                    "skills": chunk.get("skills", []),
                }
            )
        results = sorted(scored, key=lambda item: (-item["score"], item["doc_id"], item["chunk_id"]))[:top_k]
        return {"query": query, "top_k": top_k, "results": results}

    def answer(self, query: str, doc_ids: list[str] | None = None, top_k: int = 5) -> dict[str, Any]:
        retrieval = self.retrieve(query, doc_ids, top_k)
        citations = [
            {
                "doc_id": item["doc_id"],
                "chunk_id": item["chunk_id"],
                "quote": item["quote"],
                "score": item["score"],
            }
            for item in retrieval["results"]
        ]
        if not citations:
            answer = "没有在已治理的 chunk 中检索到可引用证据，因此不能生成带证据的回答。"
        else:
            fragments = "；".join(f"[{item['doc_id']} / {item['chunk_id']}] {item['quote']}" for item in citations[:3])
            answer = f"根据已治理数据中可追溯的原文片段，相关证据包括：{fragments}"
        return {"query": query, "answer": answer, "citations": citations, "retrieval": retrieval}


def query_terms(query: str) -> list[str]:
    lowered = query.casefold()
    terms = re.findall(r"[a-z0-9+#.]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    if lowered and lowered not in terms:
        terms.append(lowered)
    return [term for term in dict.fromkeys(terms) if term.strip()]


def score_chunk(text: str, terms: list[str], query: str) -> int:
    lowered = text.casefold()
    score = 0
    for term in terms:
        score += lowered.count(term) * max(1, len(term))
    if query and query.casefold() in lowered:
        score += len(query) * 2
    return score


def quote_for(text: str, terms: list[str], query: str) -> tuple[str, int, int]:
    lowered = text.casefold()
    start = -1
    if query:
        start = lowered.find(query.casefold())
    if start < 0:
        for term in terms:
            start = lowered.find(term)
            if start >= 0:
                break
    if start < 0:
        start = 0
    end = min(len(text), start + 240)
    start = max(0, start - 80)
    quote = text[start:end].strip()
    leading_trim = len(text[start:end]) - len(text[start:end].lstrip())
    return quote, start + leading_trim, start + leading_trim + len(quote)
