from __future__ import annotations

from datetime import datetime, timezone

from trend_discovery.dedup import canonical_url, cluster_documents
from trend_discovery.schemas import ExternalDocument


NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def document(
    identifier: str,
    *,
    uri: str,
    text: str,
    company: str = "示例科技",
    title: str = "AI Agent开发工程师",
    region: str = "北京",
) -> ExternalDocument:
    return ExternalDocument(
        document_id=identifier,
        source_type="job",
        source_name="企业官网",
        title=title,
        text=text,
        raw_sha256=f"sha-{identifier}",
        parser_version="test",
        company=company,
        region=region,
        uri=uri,
        collected_at=NOW,
    )


def test_canonical_url_drops_tracking_and_sorts_query() -> None:
    assert canonical_url("HTTPS://Example.COM/jobs/1/?utm_source=x&b=2&a=1#top") == (
        "https://example.com/jobs/1?a=1&b=2"
    )


def test_exact_and_near_clusters_keep_every_observation() -> None:
    first = document(
        "d1",
        uri="https://jobs.example/a?utm_source=feed",
        text="负责企业智能体平台开发，要求 Python、RAG 和大模型经验。",
    )
    exact_copy = document(
        "d2",
        uri="https://jobs.example/a",
        text="负责企业智能体平台开发，要求 Python、RAG 和大模型经验。",
    )
    near_copy = document(
        "d3",
        uri="https://jobs.example/b",
        text="负责企业智能体平台开发；要求 Python、RAG 和大模型相关经验。",
    )
    unrelated_company = document(
        "d4",
        uri="https://other.example/a",
        text="负责另一品牌的企业智能体平台开发，要求 Python、RAG 和大模型经验。",
        company="另一家公司",
    )

    result = cluster_documents([unrelated_company, near_copy, exact_copy, first], near_threshold=0.82)

    assert len(result) == 4
    assert {item.document_id for item in result.documents} == {"d1", "d2", "d3", "d4"}
    assert result.assignment_for("d1").exact_cluster_id == result.assignment_for("d2").exact_cluster_id
    assert result.assignment_for("d1").near_dup_cluster_id == result.assignment_for("d3").near_dup_cluster_id
    assert result.assignment_for("d1").near_dup_cluster_id != result.assignment_for("d4").near_dup_cluster_id
    assert result.assignment_for("d1").propagation_count == 3
    assert sum(len(values) for values in result.exact_clusters.values()) == 4


def test_cluster_ids_are_input_order_independent() -> None:
    rows = [
        document("a", uri="https://example/a", text="负责 RAG 平台开发"),
        document("b", uri="https://example/b", text="负责 RAG 平台开发与维护"),
    ]
    forward = cluster_documents(rows, near_threshold=0.70)
    reverse = cluster_documents(list(reversed(rows)), near_threshold=0.70)
    assert forward.assignments == reverse.assignments
