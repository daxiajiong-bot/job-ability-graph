from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trend_discovery.analysis import (
    analyze_trends,
    benjamini_hochberg,
    build_job_observations,
    discover_emerging_roles,
    detect_skill_updates,
)
from trend_discovery.io_utils import stable_id
from trend_discovery.kg import KGIndex
from trend_discovery.retrieval import HybridEvidenceIndex
from trend_discovery.schemas import Evidence, ExternalDocument, JobObservation


AS_OF = datetime(2026, 8, 8, tzinfo=timezone.utc)


def make_document(
    identifier: str,
    title: str,
    when: datetime,
    company: str,
    source: str,
    *,
    required: list[str],
    preferred: list[str] | None = None,
    responsibilities: list[str] | None = None,
) -> ExternalDocument:
    responsibilities = responsibilities or [f"负责{title}平台建设与工程落地 {identifier}"]
    text = "\n".join([title, *responsibilities, *required, *(preferred or []), identifier])
    return ExternalDocument(
        document_id=identifier,
        source_type="job",
        source_name=source,
        title=title,
        text=text,
        raw_sha256=stable_id("sha", identifier),
        parser_version="test",
        company=company,
        industry="人工智能",
        region="北京" if int(identifier.split("-")[-1]) % 2 == 0 else "上海",
        published_at=when,
        collected_at=when,
        metadata={
            "responsibilities": responsibilities,
            "required_skills": required,
            "preferred_skills": preferred or [],
        },
    )


def evidence_for(document: ExternalDocument) -> Evidence:
    return Evidence(
        evidence_id=f"ev:{document.document_id}",
        document_id=document.document_id,
        source_type=document.source_type,
        text=document.text,
        text_sha256=stable_id("text", document.text),
        char_start=0,
        char_end=len(document.text),
    )


def minimal_kg() -> KGIndex:
    return KGIndex(
        nodes=[
            {"node_id": "job:java-kept", "label": "Job", "properties": {"title": "Java开发工程师"}},
            {"node_id": "skill:java-kept", "label": "Skill", "properties": {"name": "Java"}},
            {"node_id": "skill:rag-kept", "label": "Skill", "properties": {"name": "RAG"}},
        ],
        edges=[],
        fingerprint="baseline-test-fingerprint",
        source_schema="jd_kg_v1",
    )


def test_build_observations_and_end_to_end_emerging_role_and_skill_update() -> None:
    documents: list[ExternalDocument] = []
    # Established role baseline: RAG absent.
    for index in range(40):
        documents.append(
            make_document(
                f"base-{index}",
                "Java开发工程师",
                AS_OF - timedelta(days=70 - index % 14),
                f"基线企业{index}",
                "官网A" if index % 2 == 0 else "官网B",
                required=["Java"],
            )
        )
    # Established role recent: strong, cross-company RAG increase.
    for index in range(40):
        documents.append(
            make_document(
                f"recent-{index}",
                "Java开发工程师",
                AS_OF - timedelta(days=20 - (index % 14)),
                f"近期企业{index}",
                "官网A" if index % 2 == 0 else "官网B",
                required=["Java", "RAG"] if index < 32 else ["Java"],
            )
        )
    # A genuinely new role, distributed over companies/sources/two snapshots.
    for index in range(8):
        documents.append(
            make_document(
                f"agent-{index}",
                "生成式AI智能体工程师",
                AS_OF - timedelta(days=22 if index < 4 else 8),
                f"智能体企业{index}",
                "企业官网" if index % 2 == 0 else "招聘平台B",
                required=["Python", "RAG", "智能体"],
                preferred=["知识图谱"],
                responsibilities=[f"负责生成式AI智能体规划、工具调用和评测体系 {index}"],
            )
        )
    job_evidence = [evidence_for(document) for document in documents]
    policy = Evidence(
        evidence_id="ev:policy-agent",
        document_id="policy-agent",
        source_type="policy",
        text="支持生成式人工智能智能体相关岗位和复合型人才培养。",
        text_sha256="policy-sha",
    )
    observations = build_job_observations(documents, [*job_evidence, policy])
    config = {
        "analysis": {
            "recent_days": 28,
            "baseline_days": 84,
            "min_cluster_size": 8,
            "min_samples": 2,
            "min_companies": 3,
            "min_week_snapshots": 2,
            "max_known_role_similarity": 0.82,
            "min_growth_rate": 1.5,
            "candidate_score_threshold": 0.65,
            "skill_min_companies": 5,
            "skill_min_share_delta": 0.10,
            "skill_min_relative_lift": 1.5,
            "significance_q": 0.05,
        }
    }

    features, emerging, updates, deltas, summary = analyze_trends(
        observations, [*job_evidence, policy], minimal_kg(), config, AS_OF
    )

    assert len(observations) == len(documents)  # duplicate analysis never destroys observations
    assert any(item.entity_name == "RAG" for item in features)
    role = next(item for item in emerging if item.canonical_title == "生成式AI智能体工程师")
    assert role.supporting_job_count == 8
    assert role.supporting_company_count == 8
    assert role.supporting_source_count == 2
    assert role.scores.overall >= 0.65
    assert role.evidence_ids and set(role.evidence_ids) <= {item.evidence_id for item in [*job_evidence, policy]}
    assert any(item.operation == "propose_node" and item.source_id == role.role_id for item in deltas)
    java_update = next(item for item in updates if item.canonical_role == "Java开发工程师")
    rag_change = next(item for item in java_update.changes if item.skill_name == "RAG")
    assert rag_change.change_type == "added"
    assert rag_change.q_value is not None and rag_change.q_value <= 0.05
    assert rag_change.kg_node_id == "skill:rag-kept"
    assert all(change.change_type != "deleted" for item in updates for change in item.changes)
    assert summary["emerging_role_count"] >= 1


def test_published_dates_cannot_fabricate_snapshot_persistence() -> None:
    """One collection run is one snapshot even when it imports old adverts."""

    collected_at = AS_OF - timedelta(days=2)
    documents = [
        make_document(
            f"backfill-{index}",
            "生成式AI安全评测工程师",
            # These two publication weeks used to create a false two-week
            # persistence signal despite all adverts arriving in one crawl.
            AS_OF - timedelta(days=22 if index < 4 else 8),
            f"回填企业{index}",
            "官网A" if index % 2 == 0 else "官网B",
            required=["Python", "大模型"],
        ).model_copy(update={"collected_at": collected_at})
        for index in range(8)
    ]
    evidence = [evidence_for(document) for document in documents]
    observations = build_job_observations(documents, evidence)

    expected_week = (collected_at - timedelta(days=collected_at.weekday())).date().isoformat()
    assert {row.snapshot_week for row in observations} == {expected_week}

    roles, _ = discover_emerging_roles(
        observations,
        evidence,
        None,
        {
            "analysis": {
                "min_cluster_size": 8,
                "min_samples": 2,
                "min_companies": 3,
                "min_week_snapshots": 2,
                "candidate_score_threshold": 0.0,
            }
        },
        AS_OF,
    )
    assert roles == []


def test_verified_snapshot_metadata_must_match_collection_week() -> None:
    collected_at = datetime(2026, 8, 7, 9, tzinfo=timezone.utc)
    document = make_document(
        "snapshot-metadata-0",
        "智能体工程师",
        datetime(2026, 6, 1, tzinfo=timezone.utc),
        "样例企业",
        "官网A",
        required=["Python"],
    ).model_copy(
        update={
            "collected_at": collected_at,
            "metadata": {"snapshot_week": "2026-W32", "snapshot_id": "crawl-2026-06-01"},
        }
    )

    observation = build_job_observations([document], [evidence_for(document)])[0]
    assert observation.snapshot_week == "2026-08-03"

def observation(
    identifier: str,
    when: datetime,
    source: str,
    skill: bool,
) -> JobObservation:
    return JobObservation(
        observation_id=identifier,
        document_id=identifier,
        source_name=source,
        title="遗留系统工程师",
        normalized_title="遗留系统工程师",
        company=f"企业-{identifier}",
        published_at=when,
        collected_at=when,
        required_skills=["LegacySkill"] if skill else [],
        evidence_ids=[f"ev:{identifier}"],
        exact_cluster_id=f"exact:{identifier}",
        near_dup_cluster_id=f"near:{identifier}",
        snapshot_week=(when - timedelta(days=when.weekday())).date().isoformat(),
    )


def test_three_cross_source_decline_is_only_removal_candidate() -> None:
    rows: list[JobObservation] = []
    # Reference period (three windows) has the skill in both sources.
    for days in (154, 126, 98):
        for source in ("官网A", "官网B"):
            for index in range(10):
                rows.append(observation(f"ref-{days}-{source}-{index}", AS_OF - timedelta(days=days), source, True))
    # Latest three non-overlapping windows retain the role but not the skill.
    for days in (70, 42, 14):
        for source in ("官网A", "官网B"):
            for index in range(10):
                rows.append(observation(f"down-{days}-{source}-{index}", AS_OF - timedelta(days=days), source, False))
    evidence = [
        Evidence(
            evidence_id=f"ev:{row.document_id}",
            document_id=row.document_id,
            source_type="job",
            text="LegacySkill" if row.required_skills else "遗留系统维护",
            text_sha256=stable_id("sha", row.document_id),
        )
        for row in rows
    ]
    updates = detect_skill_updates(
        rows,
        evidence,
        None,
        {
            "analysis": {
                "skill_min_share_delta": 0.10,
                "significance_q": 0.05,
                "skill_min_companies": 5,
            }
        },
        AS_OF,
    )
    change = next(change for update in updates for change in update.changes if change.skill_name == "LegacySkill")
    assert change.change_type == "removal_candidate"


def test_required_preferred_transition_is_modified() -> None:
    rows: list[JobObservation] = []
    for index in range(24):
        base = observation(f"preferred-{index}", AS_OF - timedelta(days=60), "官网A", False)
        rows.append(base.model_copy(update={"preferred_skills": ["GraphRAG"]}))
        rows.append(observation(f"required-{index}", AS_OF - timedelta(days=10), "官网A", True).model_copy(
            update={"required_skills": ["GraphRAG"]}
        ))
    evidence = [
        Evidence(
            evidence_id=f"ev:{row.document_id}",
            document_id=row.document_id,
            source_type="job",
            text="GraphRAG",
            text_sha256=stable_id("sha", row.document_id),
        )
        for row in rows
    ]
    updates = detect_skill_updates(rows, evidence, None, None, AS_OF)
    change = next(change for update in updates for change in update.changes if change.skill_name == "GraphRAG")
    assert change.change_type == "modified"


def test_benjamini_hochberg_is_monotone_in_rank() -> None:
    assert benjamini_hochberg([0.01, 0.02, 0.20]) == [0.03, 0.03, 0.20000000000000004]


def test_hybrid_retrieval_is_deterministic_and_filters_before_context() -> None:
    evidence = [
        Evidence(
            evidence_id="policy-rag",
            document_id="policy",
            source_type="policy",
            text="推进人工智能智能体与 RAG 工程人才培养",
            text_sha256="policy",
        ),
        Evidence(
            evidence_id="job-java",
            document_id="job",
            source_type="job",
            text="Java Spring Boot 后端工程师",
            text_sha256="job",
        ),
    ]
    index = HybridEvidenceIndex.build(evidence, embedding_dimension=64, prefer_qdrant=False)
    first = index.search("智能体 RAG", source_types=["policy"])
    second = index.search("智能体 RAG", source_types=["policy"])
    assert [item.evidence_id for item in first] == ["policy-rag"]
    assert [item.evidence_id for item in second] == ["policy-rag"]
    assert index.validate_citations(["policy-rag"], first)
    assert not index.validate_citations(["invented"], first)
