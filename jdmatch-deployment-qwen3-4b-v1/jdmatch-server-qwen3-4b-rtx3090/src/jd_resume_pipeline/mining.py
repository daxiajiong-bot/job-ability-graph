from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from .config import config_for_manifest
from .io_utils import write_json, write_jsonl
from .model_registry import resolve_model_source
from .modeling import resolve_device
from .runtime_data import load_runtime_data, violates_hard_constraints


def _stable_seed(seed: int, text: str) -> int:
    digest = hashlib.sha256(f"{seed}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _slot_map(
    resumes: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for resume in resumes:
        jd_id = str(resume["source_jd_id"])
        result.setdefault(jd_id, {})[
            str(resume["metadata"]["slot"])
        ] = resume
    return result


def _top_indices(scores: np.ndarray, count: int) -> np.ndarray:
    count = min(count, scores.shape[0])
    if count == scores.shape[0]:
        return np.argsort(-scores)
    selected = np.argpartition(scores, -count)[-count:]
    return selected[np.argsort(-scores[selected])]


def _encode(
    model: SentenceTransformer,
    texts: list[str],
    batch_size: int,
) -> np.ndarray:
    embeddings = np.asarray(
        model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        ),
        dtype=np.float32,
    )
    if not np.isfinite(embeddings).all():
        bad = int(embeddings.size - np.isfinite(embeddings).sum())
        raise FloatingPointError(
            f"embedding model returned {bad} non-finite values"
        )
    return embeddings


def _cosine_scores(
    matrix: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    """Dot normalized vectors without macOS Accelerate's spurious matmul warnings."""
    scores = np.einsum("ij,j->i", matrix, vector, optimize=True)
    if not np.isfinite(scores).all():
        raise FloatingPointError("similarity computation returned non-finite scores")
    return scores


def _cosine_score(left: np.ndarray, right: np.ndarray) -> float:
    score = float(np.einsum("i,i->", left, right, optimize=True))
    if not math.isfinite(score):
        raise FloatingPointError("similarity computation returned a non-finite score")
    return score


def mine_negatives(
    config: dict[str, Any],
    limit: int | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    data = load_runtime_data(config["paths"]["data_dir"])
    train_jds = [
        row for row in data["jds"] if row["split"] == "train"
    ]
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        queries = train_jds[:limit]
        candidate_jd_count = min(
            len(train_jds), max(100, limit * 12)
        )
        candidate_jd_ids = {
            str(row["id"]) for row in train_jds[:candidate_jd_count]
        }
    else:
        queries = train_jds
        candidate_jd_ids = {str(row["id"]) for row in train_jds}

    candidate_resumes = [
        row
        for row in data["resumes"]
        if row["split"] == "train"
        and str(row["source_jd_id"]) in candidate_jd_ids
    ]
    hard_documents = [
        row
        for row in candidate_resumes
        if row["metadata"]["slot"] in {"P1", "P2"}
    ]
    slots = _slot_map(candidate_resumes)
    for query in queries:
        if set(slots.get(str(query["id"]), {})) != {"P1", "P2", "H1"}:
            raise ValueError(f"{query['id']}: anchors unavailable for mining")

    sampling = config["sampling"]
    hardware = config["hardware"]
    device = resolve_device(
        bool(hardware["require_cuda"]),
        (
            str(hardware["required_cuda_visible_devices"])
            if hardware.get("required_cuda_visible_devices") is not None
            else None
        ),
    )
    embedding_model = SentenceTransformer(
        resolve_model_source(config, "mining_embedding"),
        device=str(device),
    )
    embedding_model.max_seq_length = int(config["text"]["max_length"])
    batch_size = int(sampling["embedding_batch_size"])

    query_embeddings = _encode(
        embedding_model,
        [str(row["text"]) for row in queries],
        batch_size,
    )
    document_embeddings = _encode(
        embedding_model,
        [str(row["text"]) for row in hard_documents],
        batch_size,
    )
    h1_documents = [slots[str(row["id"])]["H1"] for row in queries]
    h1_embeddings = _encode(
        embedding_model,
        [str(row["text"]) for row in h1_documents],
        batch_size,
    )
    critical_embeddings = _encode(
        embedding_model,
        [
            str(data["contract_by_id"][str(row["id"])][
                "omitted_requirement_text"
            ])
            for row in queries
        ],
        batch_size,
    )

    document_index = {
        str(row["id"]): index for index, row in enumerate(hard_documents)
    }
    prefiltered: dict[str, list[dict[str, Any]]] = {}
    potential_positive: dict[str, set[str]] = {}
    anchors: dict[str, dict[str, float]] = {}
    teacher_pairs: list[tuple[str, str]] = []
    teacher_pair_keys: list[tuple[str, str]] = []
    dense_top_k = int(sampling["dense_top_k"])
    prefilter_size = int(sampling["teacher_prefilter"])

    for query_index, query in enumerate(queries):
        query_id = str(query["id"])
        contract = data["contract_by_id"][query_id]
        family = str(contract.get("job_family_proxy") or "")
        cluster = str(contract["near_dup_cluster_id"])
        dense_scores = _cosine_scores(
            document_embeddings, query_embeddings[query_index]
        )
        critical_scores = _cosine_scores(
            document_embeddings, critical_embeddings[query_index]
        )

        anchor_rows = slots[query_id]
        anchor_dense = {
            slot: float(dense_scores[document_index[str(row["id"])]])
            for slot, row in anchor_rows.items()
            if str(row["id"]) in document_index
        }
        h1_embedding = h1_embeddings[query_index]
        anchor_dense["H1"] = _cosine_score(
            h1_embedding, query_embeddings[query_index]
        )
        positive_dense_floor = min(
            anchor_dense["P1"], anchor_dense["P2"]
        )
        positive_critical_floor = min(
            _cosine_score(
                document_embeddings[
                    document_index[str(anchor_rows[slot]["id"])]
                ],
                critical_embeddings[query_index],
            )
            for slot in ("P1", "P2")
        )
        h1_critical_score = _cosine_score(
            h1_embedding, critical_embeddings[query_index]
        )
        anchors[query_id] = {
            "positive_dense_floor": positive_dense_floor,
            "positive_critical_floor": positive_critical_floor,
            "h1_dense_score": anchor_dense["H1"],
            "h1_critical_score": h1_critical_score,
        }

        top = _top_indices(
            dense_scores,
            min(len(hard_documents), max(dense_top_k * 3, dense_top_k)),
        )
        candidates: list[dict[str, Any]] = []
        masks: set[str] = set()
        seen_source: set[str] = set()
        for index in top:
            document = hard_documents[int(index)]
            document_id = str(document["id"])
            source_jd_id = str(document["source_jd_id"])
            if source_jd_id == query_id:
                continue
            source_contract = data["contract_by_id"][source_jd_id]
            if str(source_contract["near_dup_cluster_id"]) == cluster:
                masks.add(document_id)
                continue
            reasons = violates_hard_constraints(
                contract, str(document["text"])
            )
            dense_score = float(dense_scores[int(index)])
            critical_score = float(critical_scores[int(index)])
            if (
                not reasons
                and dense_score >= positive_dense_floor
                and critical_score >= positive_critical_floor
            ):
                masks.add(document_id)
                continue
            critical_missing = critical_score <= h1_critical_score
            if not reasons and not critical_missing:
                masks.add(document_id)
                continue
            if source_jd_id in seen_source:
                continue
            seen_source.add(source_jd_id)
            candidates.append(
                {
                    "resume_id": document_id,
                    "source_jd_id": source_jd_id,
                    "slot": document["metadata"]["slot"],
                    "same_family": (
                        str(
                            source_contract.get("job_family_proxy") or ""
                        )
                        == family
                    ),
                    "dense_score": dense_score,
                    "critical_requirement_score": critical_score,
                    "rule_reasons": reasons,
                    "critical_requirement_missing": critical_missing,
                }
            )
            if len(candidates) >= dense_top_k:
                break
        candidates.sort(
            key=lambda item: (
                not bool(item["same_family"]),
                -float(item["dense_score"]),
            )
        )
        chosen = candidates[:prefilter_size]
        prefiltered[query_id] = chosen
        potential_positive[query_id] = masks
        for slot in ("P1", "P2", "H1"):
            row = anchor_rows[slot]
            teacher_pairs.append((str(query["text"]), str(row["text"])))
            teacher_pair_keys.append((query_id, str(row["id"])))
        for item in chosen:
            row = data["resume_by_id"][str(item["resume_id"])]
            teacher_pairs.append((str(query["text"]), str(row["text"])))
            teacher_pair_keys.append((query_id, str(row["id"])))

    reranker = CrossEncoder(
        resolve_model_source(config, "reranker"),
        device=str(device),
        max_length=int(config["text"]["max_length"]),
    )
    predictions = reranker.predict(
        teacher_pairs,
        batch_size=int(sampling["teacher_batch_size"]),
        show_progress_bar=True,
    )
    teacher_scores = {
        key: float(score)
        for key, score in zip(teacher_pair_keys, predictions)
    }

    hard_pool_size = int(sampling["hard_pool_size"])
    easy_pool_size = max(16, int(sampling["easy_random_candidates"]) // 10)
    all_candidate_indices = list(range(len(hard_documents)))
    groups: list[dict[str, Any]] = []
    pool_sizes: list[int] = []
    strict_pool_sizes: list[int] = []
    fallback_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for query_index, query in enumerate(queries):
        query_id = str(query["id"])
        contract = data["contract_by_id"][query_id]
        family = str(contract.get("job_family_proxy") or "")
        cluster = str(contract["near_dup_cluster_id"])
        anchor_rows = slots[query_id]
        positive_teacher_floor = min(
            teacher_scores[(query_id, str(anchor_rows[slot]["id"]))]
            for slot in ("P1", "P2")
        )
        h1_teacher_score = teacher_scores[
            (query_id, str(anchor_rows["H1"]["id"]))
        ]
        strict_verified: list[dict[str, Any]] = []
        teacher_reviewed: list[dict[str, Any]] = []
        masks = set(potential_positive[query_id])
        for item in prefiltered[query_id]:
            document_id = str(item["resume_id"])
            teacher_score = teacher_scores[(query_id, document_id)]
            has_mismatch = bool(item["rule_reasons"]) or bool(
                item["critical_requirement_missing"]
            )
            if teacher_score >= positive_teacher_floor and not bool(
                item["rule_reasons"]
            ):
                masks.add(document_id)
                continue
            if teacher_score < h1_teacher_score or not has_mismatch:
                if not has_mismatch:
                    continue
            reasons = list(item["rule_reasons"])
            if item["critical_requirement_missing"]:
                reasons.append("critical_requirement_missing")
            reviewed = {
                **item,
                "reranker_score": teacher_score,
                "reasons": reasons,
            }
            teacher_reviewed.append(reviewed)
            if teacher_score >= h1_teacher_score:
                strict_verified.append(
                    {**reviewed, "selection_tier": "strict_teacher"}
                )
        strict_verified.sort(
            key=lambda item: (
                not bool(item["same_family"]),
                -float(item["reranker_score"]),
                -float(item["dense_score"]),
            )
        )
        strict_pool_sizes.append(len(strict_verified))
        verified = [
            item for item in strict_verified if bool(item["same_family"])
        ][:hard_pool_size]
        selected_ids = {str(item["resume_id"]) for item in verified}
        relaxed = [
            item
            for item in teacher_reviewed
            if str(item["resume_id"]) not in selected_ids
        ]
        relaxed.sort(
            key=lambda item: (
                not bool(item["same_family"]),
                -float(item["reranker_score"]),
                -float(item["dense_score"]),
            )
        )
        for item in relaxed:
            if len(verified) >= hard_pool_size:
                break
            if not bool(item["same_family"]):
                continue
            tier = (
                "same_family_teacher_fallback"
            )
            fallback_counts[tier] += 1
            verified.append({**item, "selection_tier": tier})
            selected_ids.add(str(item["resume_id"]))
        for item in strict_verified:
            if len(verified) >= hard_pool_size:
                break
            if str(item["resume_id"]) in selected_ids:
                continue
            verified.append(item)
            selected_ids.add(str(item["resume_id"]))
        for item in relaxed:
            if len(verified) >= hard_pool_size:
                break
            if str(item["resume_id"]) in selected_ids:
                continue
            fallback_counts["cross_family_teacher_fallback"] += 1
            verified.append(
                {**item, "selection_tier": "cross_family_teacher_fallback"}
            )
            selected_ids.add(str(item["resume_id"]))
        for item in verified:
            for reason in item["reasons"]:
                reason_counts[reason] += 1

        rng = random.Random(_stable_seed(int(config["seed"]), query_id))
        random_indices = rng.sample(
            all_candidate_indices,
            min(
                int(sampling["easy_random_candidates"]),
                len(all_candidate_indices),
            ),
        )
        easy_candidates: list[tuple[float, str]] = []
        for index in random_indices:
            document = hard_documents[index]
            source_jd_id = str(document["source_jd_id"])
            if source_jd_id == query_id:
                continue
            source_contract = data["contract_by_id"][source_jd_id]
            if str(source_contract["near_dup_cluster_id"]) == cluster:
                continue
            if (
                str(source_contract.get("job_family_proxy") or "")
                == family
            ):
                continue
            score = _cosine_score(
                document_embeddings[index], query_embeddings[query_index]
            )
            easy_candidates.append((score, str(document["id"])))
        easy_candidates.sort()
        cutoff = max(
            1,
            math.ceil(
                len(easy_candidates) * float(sampling["easy_quantile"])
            ),
        )
        easy_ids = [item[1] for item in easy_candidates[:cutoff]]
        rng.shuffle(easy_ids)
        easy_ids = easy_ids[:easy_pool_size]
        pool_sizes.append(len(verified))
        groups.append(
            {
                "query_id": query_id,
                "positive_ids": [
                    str(anchor_rows["P1"]["id"]),
                    str(anchor_rows["P2"]["id"]),
                ],
                "near_miss_id": str(anchor_rows["H1"]["id"]),
                "hard_negative_pool": verified,
                "easy_negative_pool": easy_ids,
                "do_not_use_as_negative": sorted(masks),
                "anchor_scores": {
                    **anchors[query_id],
                    "positive_reranker_floor": positive_teacher_floor,
                    "h1_reranker_score": h1_teacher_score,
                },
            }
        )

    target_dir = Path(
        output_dir
        if output_dir is not None
        else Path(config["paths"]["run_dir"]) / "negative_mining"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    groups_path = target_dir / "train_groups.jsonl"
    write_jsonl(groups_path, groups)
    cache_dir = target_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(cache_dir / "query_embeddings.npy", query_embeddings)
    np.save(cache_dir / "document_embeddings.npy", document_embeddings)
    write_jsonl(
        cache_dir / "query_ids.jsonl",
        [{"id": row["id"]} for row in queries],
    )
    write_jsonl(
        cache_dir / "document_ids.jsonl",
        [{"id": row["id"]} for row in hard_documents],
    )
    summary = {
        "schema_version": "negative_sampling_v1",
        "config": config_for_manifest(config),
        "limit": limit,
        "queries": len(queries),
        "candidate_documents": len(hard_documents),
        "groups_output": str(groups_path.resolve()),
        "hard_pool": {
            "mean": round(float(np.mean(pool_sizes)), 4),
            "min": min(pool_sizes) if pool_sizes else 0,
            "max": max(pool_sizes) if pool_sizes else 0,
            "strict_teacher_mean": round(
                float(np.mean(strict_pool_sizes)), 4
            ),
            "groups_with_at_least_2": sum(size >= 2 for size in pool_sizes),
            "groups_with_at_least_6": sum(size >= 6 for size in pool_sizes),
        },
        "fallback_counts": dict(fallback_counts),
        "reason_counts": dict(reason_counts),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    write_json(target_dir / "manifest.json", summary)
    return summary
