from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from .io_utils import write_json
from .model_registry import resolve_model_source
from .modeling import load_trainable_encoder, resolve_device
from .runtime_data import load_runtime_data


def _normalize(values: np.ndarray) -> np.ndarray:
    if not np.isfinite(values).all():
        raise FloatingPointError("embedding array contains non-finite values")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    normalized = values / np.maximum(norms, 1e-12)
    if not np.isfinite(normalized).all():
        raise FloatingPointError("normalized embeddings contain non-finite values")
    return normalized


def _scores(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    values = np.einsum("ij,j->i", matrix, vector, optimize=True)
    if not np.isfinite(values).all():
        raise FloatingPointError("evaluation scores contain non-finite values")
    return values


def _frozen_encode_function(
    config: dict[str, Any],
    model_name: str,
    model_key: str,
) -> Callable[[list[str], bool], np.ndarray]:
    hardware = config["hardware"]
    device = resolve_device(
        bool(hardware["require_cuda"]),
        (
            str(hardware["required_cuda_visible_devices"])
            if hardware.get("required_cuda_visible_devices") is not None
            else None
        ),
    )
    model = SentenceTransformer(
        resolve_model_source(config, model_key),
        device=str(device),
    )
    model.max_seq_length = int(config["text"]["max_length"])
    instruction = str(config["models"]["query_instruction"])
    output_dimension = int(config["text"]["output_dimension"])
    batch_size = int(config["evaluation"]["embedding_batch_size"])

    def encode(texts: list[str], is_query: bool) -> np.ndarray:
        prepared = (
            [f"Instruct: {instruction}\nQuery:{text}" for text in texts]
            if is_query and "qwen" in model_name.lower()
            else texts
        )
        values = np.asarray(
            model.encode(
                prepared,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=True,
                convert_to_numpy=True,
            ),
            dtype=np.float32,
        )
        if not np.isfinite(values).all():
            raise FloatingPointError(
                f"{model_name} returned non-finite evaluation embeddings"
            )
        dimension = min(output_dimension, values.shape[1])
        return _normalize(values[:, :dimension])

    return encode


def _adapter_encode_function(
    config: dict[str, Any],
    adapter_path: str | Path,
) -> Callable[[list[str], bool], np.ndarray]:
    encoder = load_trainable_encoder(config, adapter_path=adapter_path)
    encoder.model.eval()
    batch_size = int(config["evaluation"]["embedding_batch_size"])

    def encode(texts: list[str], is_query: bool) -> np.ndarray:
        values: list[np.ndarray] = []
        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                embedding = encoder.encode_texts(
                    texts[start : start + batch_size],
                    is_query=is_query,
                )
                array = embedding.cpu().numpy()
                if not np.isfinite(array).all():
                    raise FloatingPointError(
                        "trained adapter returned non-finite embeddings"
                    )
                values.append(array)
        return np.concatenate(values, axis=0)

    return encode


def _metrics_for_split(
    data: dict[str, Any],
    split: str,
    encode: Callable[[list[str], bool], np.ndarray],
    recall_k: list[int],
    limit: int | None,
) -> dict[str, Any]:
    queries = [
        row for row in data["jds"] if row["split"] == split
    ]
    if limit is not None:
        queries = queries[:limit]
    documents: list[dict[str, Any]] = []
    group_slices: list[tuple[int, int]] = []
    for query in queries:
        start = len(documents)
        values = sorted(
            data["resumes_by_jd"][str(query["id"])],
            key=lambda row: str(row["id"]),
        )
        documents.extend(values)
        group_slices.append((start, len(documents)))
    query_embeddings = encode(
        [str(row["text"]) for row in queries], True
    )
    document_embeddings = encode(
        [str(row["text"]) for row in documents], False
    )

    pairwise_correct = 0
    pairwise_total = 0
    strict_triplet_success = 0
    reciprocal_ranks: list[float] = []
    ndcg_values: list[float] = []
    recalls: dict[int, list[float]] = {value: [] for value in recall_k}
    full_reciprocal_ranks: list[float] = []
    full_ndcg_values: list[float] = []
    full_positive_ranks: list[int] = []
    full_recalls: dict[int, list[float]] = {
        value: [] for value in recall_k
    }
    full_cutoff = max(recall_k) if recall_k else 10
    ideal_dcg = 1.0 + 1.0 / math.log2(3)
    for index, query in enumerate(queries):
        start, end = group_slices[index]
        values = documents[start:end]
        scores = _scores(
            document_embeddings[start:end], query_embeddings[index]
        )
        labels = np.asarray(
            [
                0 if row["metadata"]["slot"] == "H1" else 1
                for row in values
            ],
            dtype=np.int64,
        )
        positive_scores = scores[labels == 1]
        negative_score = float(scores[labels == 0][0])
        pairwise_correct += int(positive_scores[0] > negative_score)
        pairwise_correct += int(positive_scores[1] > negative_score)
        pairwise_total += 2
        strict_triplet_success += int(
            float(np.min(positive_scores)) > negative_score
        )
        order = np.argsort(-scores)
        ranked = labels[order]
        first_positive = int(np.flatnonzero(ranked == 1)[0]) + 1
        reciprocal_ranks.append(1.0 / first_positive)
        dcg = sum(
            float(label) / math.log2(rank + 2)
            for rank, label in enumerate(ranked)
        )
        ndcg_values.append(dcg / ideal_dcg)
        for k in recall_k:
            recalls[k].append(
                float(ranked[: min(k, len(ranked))].sum()) / 2.0
            )

        global_scores = _scores(
            document_embeddings, query_embeddings[index]
        )
        global_order = np.argsort(-global_scores)
        own_positive_indices = {
            document_index
            for document_index in range(start, end)
            if documents[document_index]["metadata"]["slot"] in {"P1", "P2"}
        }
        positive_ranks = sorted(
            rank + 1
            for rank, document_index in enumerate(global_order)
            if int(document_index) in own_positive_indices
        )
        full_positive_ranks.extend(positive_ranks)
        full_reciprocal_ranks.append(1.0 / positive_ranks[0])
        full_dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank in positive_ranks
            if rank <= full_cutoff
        )
        full_ndcg_values.append(full_dcg / ideal_dcg)
        for k in recall_k:
            full_recalls[k].append(
                sum(rank <= k for rank in positive_ranks) / 2.0
            )
    count = len(queries)
    return {
        "split": split,
        "queries": count,
        "triplet_diagnostics": {
            "candidate_pool": "source_triplet_only",
            "pairwise_p_over_h1_accuracy": (
                pairwise_correct / pairwise_total if pairwise_total else 0.0
            ),
            "strict_both_positives_over_h1": (
                strict_triplet_success / count if count else 0.0
            ),
            "mrr": float(np.mean(reciprocal_ranks)) if count else 0.0,
            "ndcg_at_3": float(np.mean(ndcg_values)) if count else 0.0,
            "recall": {
                str(k): float(np.mean(values)) if values else 0.0
                for k, values in recalls.items()
            },
        },
        "full_split_retrieval": {
            "candidate_pool": "all_source_triplets_in_evaluated_split",
            "candidate_documents": len(documents),
            "known_relevant_per_query": 2,
            "mrr": (
                float(np.mean(full_reciprocal_ranks)) if count else 0.0
            ),
            f"ndcg_at_{full_cutoff}": (
                float(np.mean(full_ndcg_values)) if count else 0.0
            ),
            "mean_known_positive_rank": (
                float(np.mean(full_positive_ranks))
                if full_positive_ranks
                else 0.0
            ),
            "recall": {
                str(k): float(np.mean(values)) if values else 0.0
                for k, values in full_recalls.items()
            },
            "caveat": (
                "Only each JD's generated P1/P2 are labeled relevant. "
                "Other suitable cross-JD resumes may be unlabeled."
            ),
        },
    }


def evaluate_encoder(
    config: dict[str, Any],
    model_name: str | None = None,
    adapter_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    started = time.time()
    data = load_runtime_data(config["paths"]["data_dir"])
    if adapter_path is not None:
        encode = _adapter_encode_function(config, adapter_path)
        identity = str(Path(adapter_path).resolve())
    else:
        identity = str(model_name or config["models"]["embedding"])
        model_key = (
            "embedding"
            if identity == str(config["models"]["embedding"])
            else "mining_embedding"
        )
        encode = _frozen_encode_function(config, identity, model_key)
    results = [
        _metrics_for_split(
            data,
            split=str(split),
            encode=encode,
            recall_k=[int(k) for k in config["evaluation"]["recall_k"]],
            limit=limit,
        )
        for split in config["evaluation"]["splits"]
    ]
    return {
        "model": identity,
        "adapter": adapter_path is not None,
        "limit": limit,
        "results": results,
        "elapsed_seconds": round(time.time() - started, 3),
        "warning": (
            "Metrics use synthetic labels and are not a substitute for "
            "a cross-JD human-judged evaluation set."
        ),
    }


def run_baselines(
    config: dict[str, Any],
    limit: int | None = None,
) -> dict[str, Any]:
    models = []
    for name in (
        str(config["models"]["mining_embedding"]),
        str(config["models"]["embedding"]),
    ):
        if name not in models:
            models.append(name)
    results = [
        evaluate_encoder(config, model_name=name, limit=limit)
        for name in models
    ]
    target = Path(config["paths"]["run_dir"]) / "baselines"
    target.mkdir(parents=True, exist_ok=True)
    payload = {"models": results}
    write_json(target / "metrics.json", payload)
    return payload


def evaluate_trained(
    config: dict[str, Any],
    adapter_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    target_adapter = (
        Path(adapter_path)
        if adapter_path is not None
        else Path(config["paths"]["run_dir"]) / "best_adapter"
    )
    if not target_adapter.is_dir():
        raise ValueError(f"trained adapter is missing: {target_adapter}")
    payload = evaluate_encoder(
        config,
        adapter_path=target_adapter,
        limit=limit,
    )
    target = Path(config["paths"]["run_dir"]) / "evaluation"
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / "metrics.json", payload)
    return payload
