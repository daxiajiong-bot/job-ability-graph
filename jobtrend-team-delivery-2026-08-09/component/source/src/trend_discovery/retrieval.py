"""Hybrid evidence retrieval with an offline deterministic fallback."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np

from .schemas import Evidence, SourceType


def _as_evidence(value: Evidence | Mapping[str, object]) -> Evidence:
    return value if isinstance(value, Evidence) else Evidence.model_validate(value)


def lexical_terms(value: str) -> list[str]:
    """Tokenise Chinese/Latin evidence without a network model or dictionary."""

    value = value.casefold()
    terms = re.findall(r"[a-z0-9][a-z0-9_+#.\-/]*|[\u4e00-\u9fff]+", value)
    output: list[str] = []
    for term in terms:
        output.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 1:
            output.extend(term[index : index + 2] for index in range(len(term) - 1))
    return output


def hash_embedding(text: str, dimension: int = 256) -> np.ndarray:
    """Stable feature-hashed embedding used for tests/offline cache replay."""

    if dimension <= 0:
        raise ValueError("dimension must be positive")
    vector = np.zeros(dimension, dtype=np.float32)
    counts = Counter(lexical_terms(text))
    for term, count in counts.items():
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dimension
        vector[index] += 1.0 + math.log(count)
    norm = float(np.linalg.norm(vector))
    if norm:
        vector /= norm
    return vector


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence: Evidence
    score: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rerank_score: float | None = None

    @property
    def evidence_id(self) -> str:
        return self.evidence.evidence_id

    @property
    def document_id(self) -> str:
        return self.evidence.document_id

    def model_dump(self, mode: str = "python") -> dict[str, object]:
        return {
            "evidence": self.evidence.model_dump(mode=mode),
            "score": self.score,
            "dense_rank": self.dense_rank,
            "lexical_rank": self.lexical_rank,
            "rerank_score": self.rerank_score,
        }


class HybridEvidenceIndex:
    """Dense + lexical RRF index.

    When ``qdrant_path`` is supplied and qdrant-client can initialise a local
    store, dense retrieval is delegated to Qdrant.  All data is also retained
    in memory so a missing/incompatible optional client cannot break offline
    analysis or deterministic tests.
    """

    def __init__(
        self,
        evidence: Sequence[Evidence],
        vectors: np.ndarray,
        *,
        dimension: int,
        embedder: Callable[[str], Sequence[float]] | None,
        qdrant_client: object | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.evidence = tuple(evidence)
        self.by_id = {item.evidence_id: item for item in evidence}
        self.dimension = dimension
        self.embedder = embedder
        self.vectors = vectors
        self.backend = "qdrant-local" if qdrant_client is not None else "memory"
        self._qdrant = qdrant_client
        self._collection_name = collection_name
        self._term_counts = [Counter(lexical_terms(item.text)) for item in evidence]
        self._doc_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            self._doc_frequency.update(counts.keys())
        self._average_length = (
            sum(sum(counts.values()) for counts in self._term_counts) / len(self._term_counts)
            if self._term_counts
            else 0.0
        )

    @classmethod
    def build(
        cls,
        evidence: Sequence[Evidence | Mapping[str, object]],
        *,
        qdrant_path: str | Path | None = None,
        embedding_dimension: int = 256,
        embedder: Callable[[str], Sequence[float]] | None = None,
        prefer_qdrant: bool = True,
        collection_name: str | None = None,
    ) -> "HybridEvidenceIndex":
        parsed = tuple(_as_evidence(item) for item in evidence)
        identifiers = [item.evidence_id for item in parsed]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evidence_id values must be unique")

        def embed(text: str) -> np.ndarray:
            vector = np.asarray(
                embedder(text) if embedder is not None else hash_embedding(text, embedding_dimension),
                dtype=np.float32,
            )
            if vector.ndim != 1:
                raise ValueError("embedder must return a one-dimensional vector")
            if vector.shape[0] != embedding_dimension:
                raise ValueError(
                    f"embedder returned dimension {vector.shape[0]}, expected {embedding_dimension}"
                )
            norm = float(np.linalg.norm(vector))
            return vector / norm if norm else vector

        vectors = (
            np.vstack([embed(item.text) for item in parsed])
            if parsed
            else np.empty((0, embedding_dimension), dtype=np.float32)
        )
        client: object | None = None
        selected_collection: str | None = None
        if qdrant_path is not None and prefer_qdrant and parsed:
            try:
                from qdrant_client import QdrantClient, models

                target = Path(qdrant_path).expanduser().resolve()
                target.mkdir(parents=True, exist_ok=True)
                client = QdrantClient(path=str(target))
                collection_signature = "\n".join(
                    [
                        str(embedding_dimension),
                        *(f"{item.evidence_id}:{item.text_sha256}" for item in sorted(parsed, key=lambda row: row.evidence_id)),
                    ]
                )
                suffix = hashlib.sha256(collection_signature.encode("utf-8")).hexdigest()[:12]
                selected_collection = collection_name or f"jobtrend_evidence_{suffix}"
                exists = bool(client.collection_exists(selected_collection))
                if not exists:
                    client.create_collection(
                        collection_name=selected_collection,
                        vectors_config=models.VectorParams(
                            size=embedding_dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                    points = [
                        models.PointStruct(
                            id=str(uuid.UUID(hashlib.md5(item.evidence_id.encode("utf-8")).hexdigest())),
                            vector=vectors[index].tolist(),
                            payload={"evidence_id": item.evidence_id},
                        )
                        for index, item in enumerate(parsed)
                    ]
                    client.upsert(collection_name=selected_collection, points=points, wait=True)
            except Exception:
                # Local Qdrant is an acceleration/persistence option, not an
                # availability dependency.  Search remains exactly functional.
                client, selected_collection = None, None
        return cls(
            parsed,
            vectors,
            dimension=embedding_dimension,
            embedder=embedder,
            qdrant_client=client,
            collection_name=selected_collection,
        )

    def _embed_query(self, query: str) -> np.ndarray:
        vector = np.asarray(
            self.embedder(query) if self.embedder is not None else hash_embedding(query, self.dimension),
            dtype=np.float32,
        )
        if vector.shape != (self.dimension,):
            raise ValueError(f"query embedder returned {vector.shape}, expected ({self.dimension},)")
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def _allowed_indices(
        self,
        *,
        source_types: set[SourceType] | None,
        document_ids: set[str] | None,
        allowed_evidence_ids: set[str] | None,
        predicate: Callable[[Evidence], bool] | None,
    ) -> list[int]:
        result: list[int] = []
        for index, item in enumerate(self.evidence):
            if source_types is not None and item.source_type not in source_types:
                continue
            if document_ids is not None and item.document_id not in document_ids:
                continue
            if allowed_evidence_ids is not None and item.evidence_id not in allowed_evidence_ids:
                continue
            if predicate is not None and not predicate(item):
                continue
            result.append(index)
        return result

    def _dense_ranking(self, query_vector: np.ndarray, allowed: set[int], limit: int) -> list[int]:
        if not allowed or limit <= 0:
            return []
        if self._qdrant is not None and self._collection_name:
            try:
                client = self._qdrant
                if hasattr(client, "query_points"):
                    response = client.query_points(
                        collection_name=self._collection_name,
                        query=query_vector.tolist(),
                        limit=min(len(self.evidence), max(limit * 4, limit)),
                        with_payload=True,
                    )
                    points = response.points
                else:
                    points = client.search(
                        collection_name=self._collection_name,
                        query_vector=query_vector.tolist(),
                        limit=min(len(self.evidence), max(limit * 4, limit)),
                        with_payload=True,
                    )
                by_identifier = {item.evidence_id: index for index, item in enumerate(self.evidence)}
                ranking = [
                    by_identifier[str(point.payload["evidence_id"])]
                    for point in points
                    if point.payload
                    and str(point.payload.get("evidence_id")) in by_identifier
                    and by_identifier[str(point.payload["evidence_id"])] in allowed
                ]
                if len(ranking) >= min(limit, len(allowed)):
                    return ranking[:limit]
            except Exception:
                pass
        scored = [(float(np.dot(query_vector, self.vectors[index])), index) for index in allowed]
        scored.sort(key=lambda value: (-value[0], self.evidence[value[1]].evidence_id))
        return [index for _, index in scored[:limit]]

    def _lexical_score(self, query_terms: Counter[str], index: int) -> float:
        counts = self._term_counts[index]
        length = max(1, sum(counts.values()))
        score = 0.0
        total = max(1, len(self.evidence))
        for term, query_count in query_terms.items():
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            document_frequency = self._doc_frequency.get(term, 0)
            inverse_frequency = math.log(1.0 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
            normaliser = frequency + 1.2 * (
                0.25 + 0.75 * length / max(1.0, self._average_length)
            )
            score += query_count * inverse_frequency * frequency * 2.2 / normaliser
        return score

    def search(
        self,
        query: str,
        *,
        dense_top_k: int = 50,
        sparse_top_k: int = 50,
        fused_top_k: int = 50,
        rerank_top_k: int = 8,
        source_types: Iterable[SourceType] | None = None,
        document_ids: Iterable[str] | None = None,
        allowed_evidence_ids: Iterable[str] | None = None,
        predicate: Callable[[Evidence], bool] | None = None,
        reranker: Callable[[str, Sequence[Evidence]], Sequence[float]] | None = None,
        rrf_k: int = 60,
    ) -> list[RetrievalHit]:
        """Search and filter evidence before exposing it to generation."""

        if not query.strip() or rerank_top_k <= 0:
            return []
        allowed_indices = self._allowed_indices(
            source_types=set(source_types) if source_types is not None else None,
            document_ids=set(document_ids) if document_ids is not None else None,
            allowed_evidence_ids=set(allowed_evidence_ids) if allowed_evidence_ids is not None else None,
            predicate=predicate,
        )
        allowed = set(allowed_indices)
        dense = self._dense_ranking(self._embed_query(query), allowed, dense_top_k)
        query_terms = Counter(lexical_terms(query))
        lexical_scores = [(self._lexical_score(query_terms, index), index) for index in allowed]
        lexical_scores.sort(key=lambda value: (-value[0], self.evidence[value[1]].evidence_id))
        sparse = [index for score, index in lexical_scores if score > 0][:sparse_top_k]
        dense_rank = {index: rank for rank, index in enumerate(dense, start=1)}
        sparse_rank = {index: rank for rank, index in enumerate(sparse, start=1)}
        fused: list[tuple[float, int]] = []
        for index in set(dense) | set(sparse):
            score = 0.0
            if index in dense_rank:
                score += 1.0 / (rrf_k + dense_rank[index])
            if index in sparse_rank:
                score += 1.0 / (rrf_k + sparse_rank[index])
            fused.append((score, index))
        fused.sort(key=lambda value: (-value[0], self.evidence[value[1]].evidence_id))
        fused = fused[:fused_top_k]

        rerank_scores: dict[int, float] = {}
        if reranker is not None and fused:
            values = list(reranker(query, [self.evidence[index] for _, index in fused]))
            if len(values) != len(fused):
                raise ValueError("reranker must return one score per evidence item")
            rerank_scores = {index: float(values[position]) for position, (_, index) in enumerate(fused)}
            fused.sort(key=lambda value: (-rerank_scores[value[1]], -value[0], self.evidence[value[1]].evidence_id))

        return [
            RetrievalHit(
                evidence=self.evidence[index],
                score=float(rerank_scores.get(index, score)),
                dense_rank=dense_rank.get(index),
                lexical_rank=sparse_rank.get(index),
                rerank_score=rerank_scores.get(index),
            )
            for score, index in fused[:rerank_top_k]
        ]

    @staticmethod
    def validate_citations(citation_ids: Iterable[str], hits: Sequence[RetrievalHit]) -> bool:
        """Return true only when every generated citation was in the context."""

        allowed = {hit.evidence_id for hit in hits}
        citations = list(citation_ids)
        return bool(citations) and all(identifier in allowed for identifier in citations)

    def close(self) -> None:
        """Release a local Qdrant/SQLite handle when one was opened."""

        if self._qdrant is not None and hasattr(self._qdrant, "close"):
            self._qdrant.close()


__all__ = ["HybridEvidenceIndex", "RetrievalHit", "hash_embedding", "lexical_terms"]
