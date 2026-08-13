from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence


@dataclass(frozen=True)
class ClassificationMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def classification_metrics(
    predicted: Iterable[Hashable], expected: Iterable[Hashable]
) -> ClassificationMetrics:
    """Return set-based precision/recall/F1 for extraction evaluation."""

    predicted_set = set(predicted)
    expected_set = set(expected)
    true_positive = len(predicted_set & expected_set)
    false_positive = len(predicted_set - expected_set)
    false_negative = len(expected_set - predicted_set)
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    return ClassificationMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def precision_at_k(ranked_ids: Sequence[Hashable], relevant_ids: Iterable[Hashable], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = set(relevant_ids)
    retrieved = list(ranked_ids[:k])
    if not retrieved:
        return 0.0
    return sum(1 for item in retrieved if item in relevant) / len(retrieved)


def recall_at_k(ranked_ids: Sequence[Hashable], relevant_ids: Iterable[Hashable], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def pairwise_dedup_precision(
    predicted_pairs: Iterable[tuple[Hashable, Hashable]],
    duplicate_pairs: Iterable[tuple[Hashable, Hashable]],
) -> float:
    predicted = {_canonical_pair(pair) for pair in predicted_pairs}
    expected = {_canonical_pair(pair) for pair in duplicate_pairs}
    if not predicted:
        return 1.0
    return len(predicted & expected) / len(predicted)


def _canonical_pair(pair: tuple[Hashable, Hashable]) -> frozenset[Hashable]:
    left, right = pair
    if left == right:
        raise ValueError("a duplicate pair must contain two distinct identifiers")
    return frozenset((left, right))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
