from trend_discovery.evaluation import (
    classification_metrics,
    pairwise_dedup_precision,
    precision_at_k,
    recall_at_k,
)


def test_classification_metrics() -> None:
    result = classification_metrics({"Java", "RAG"}, {"Java", "MCP"})
    assert result.precision == 0.5
    assert result.recall == 0.5
    assert result.f1 == 0.5


def test_rank_metrics() -> None:
    ranked = ["e1", "e2", "e3"]
    assert precision_at_k(ranked, {"e1", "e3"}, 2) == 0.5
    assert recall_at_k(ranked, {"e1", "e3"}, 2) == 0.5
    assert recall_at_k(ranked, set(), 20) == 1.0


def test_pairwise_dedup_precision_is_order_independent() -> None:
    predicted = [("a", "b"), ("a", "c")]
    expected = [("b", "a")]
    assert pairwise_dedup_precision(predicted, expected) == 0.5
