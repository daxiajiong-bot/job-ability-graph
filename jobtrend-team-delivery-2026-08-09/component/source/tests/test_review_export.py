from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trend_discovery.exporter import (
    REQUIRED_DATA_FILES,
    REQUIRED_HANDOFF_FILES,
    assert_safe_for_handoff,
    build_handoff_bundle,
)
from trend_discovery.io_utils import read_jsonl, sha256_file, write_jsonl
from trend_discovery.review import export_review_queue, import_review_queue
from trend_discovery.schemas import (
    EmergingRole,
    EmergingRoleScores,
    Evidence,
    ExternalDocument,
    JobSkillUpdate,
    KGLinkDelta,
    RoleAbility,
    SkillChange,
    TrendFeature,
    TrendMetrics,
    TrendWindow,
)


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _role() -> EmergingRole:
    skill = RoleAbility(
        name="Python",
        category="Tech",
        role="required",
        confidence=0.9,
        evidence_ids=["ev-1"],
    )
    scores = EmergingRoleScores(
        novelty=0.8,
        growth=0.8,
        persistence=0.8,
        source_diversity=0.8,
        evidence_coverage=1.0,
        overall=0.82,
    )
    return EmergingRole(
        role_id="role-1",
        canonical_title="AI Agent 工程师",
        core_responsibilities=["构建智能体"],
        required_skills=[skill],
        preferred_skills=[],
        typical_industry_scenarios=["企业服务"],
        first_seen=NOW - timedelta(days=14),
        last_seen=NOW,
        supporting_job_count=10,
        supporting_company_count=4,
        supporting_source_count=2,
        scores=scores,
        evidence_ids=["ev-1"],
        explanation="统计门槛通过",
    )


def _window() -> TrendWindow:
    return TrendWindow(
        recent_start=NOW - timedelta(days=28),
        recent_end=NOW,
        baseline_start=NOW - timedelta(days=112),
        baseline_end=NOW - timedelta(days=28),
    )


def _update() -> JobSkillUpdate:
    return JobSkillUpdate(
        update_id="update-1",
        canonical_role="Java 开发工程师",
        window=_window(),
        changes=[
            SkillChange(
                skill_name="大模型应用开发",
                change_type="rising",
                baseline_share=0.1,
                recent_share=0.3,
                share_delta=0.2,
                relative_lift=3.0,
                supporting_company_count=6,
                evidence_ids=["ev-1"],
            )
        ],
        evidence_ids=["ev-1"],
        explanation="跨来源增长",
    )


def _delta() -> KGLinkDelta:
    return KGLinkDelta(
        delta_id="delta-1",
        baseline_graph_fingerprint="graph-sha",
        operation="link_existing",
        source_id="Python",
        target_id="kg-skill-1",
        relation_type="ALIAS_OF",
        evidence_ids=["ev-1"],
        resolution_status="review_candidate",
        properties={"canonical_name": "Python"},
    )


def _write_review_inputs(directory: Path) -> tuple[Path, Path, Path]:
    roles = directory / "emerging_roles.jsonl"
    updates = directory / "job_skill_updates.jsonl"
    deltas = directory / "kg_link_delta.jsonl"
    write_jsonl(roles, [_role()])
    write_jsonl(updates, [_update()])
    write_jsonl(deltas, [_delta()])
    return roles, updates, deltas


def test_review_roundtrip_is_non_destructive(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    roles, updates, deltas = _write_review_inputs(source)
    queue = source / "review_queue.csv"
    assert export_review_queue(
        queue,
        emerging_roles_path=roles,
        job_skill_updates_path=updates,
        kg_link_delta_path=deltas,
    ) == 3
    original_hashes = {path: sha256_file(path) for path in (roles, updates, deltas)}

    with queue.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    for row in rows:
        if row["object_type"] == "emerging_role":
            row["decision"] = "approved"
            row["reviewer"] = "reviewer-a"
            row["reviewed_at"] = "2026-08-08T12:00:00+08:00"
            row["canonical_title"] = "生成式 AI 智能体工程师"
            row["edits_json"] = json.dumps({"aliases": ["Agent 工程师"]}, ensure_ascii=False)
        elif row["object_type"] == "ability_mapping":
            row["decision"] = "rejected"
            row["reviewer"] = "reviewer-a"
    with queue.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    result = import_review_queue(
        queue,
        tmp_path / "reviewed",
        emerging_roles_path=roles,
        job_skill_updates_path=updates,
        kg_link_delta_path=deltas,
    )
    assert result["reviewed"] == 2
    assert all(sha256_file(path) == digest for path, digest in original_hashes.items())
    reviewed_role = next(read_jsonl(tmp_path / "reviewed" / "emerging_roles.jsonl"))
    assert reviewed_role["status"] == "approved"
    assert reviewed_role["canonical_title"] == "生成式 AI 智能体工程师"
    assert reviewed_role["aliases"] == ["Agent 工程师"]
    reviewed_delta = next(read_jsonl(tmp_path / "reviewed" / "kg_link_delta.jsonl"))
    assert reviewed_delta["resolution_status"] == "unresolved"
    assert reviewed_delta["properties"]["review_status"] == "rejected"
    assert sum(1 for _ in read_jsonl(tmp_path / "reviewed" / "review_decisions.jsonl")) == 2


def _write_bundle_inputs(directory: Path) -> None:
    directory.mkdir()
    document = ExternalDocument(
        document_id="doc-1",
        source_type="job",
        source_name="company-careers",
        title="AI Agent 工程师",
        text="需要 Python",
        raw_sha256="a" * 64,
        parser_version="test",
        company="示例公司",
        collected_at=NOW,
    )
    evidence = Evidence(
        evidence_id="ev-1",
        document_id="doc-1",
        source_type="job",
        text="需要 Python",
        text_sha256="b" * 64,
        char_start=0,
        char_end=9,
    )
    trend = TrendFeature(
        trend_id="trend-1",
        entity_type="job_role",
        entity_name="AI Agent 工程师",
        window=_window(),
        metrics=TrendMetrics(distinct_job_count=10, distinct_company_count=4),
        score=0.8,
        confidence=0.8,
        evidence_ids=["ev-1"],
    )
    write_jsonl(directory / "external_documents.jsonl", [document])
    write_jsonl(directory / "evidence.jsonl", [evidence])
    write_jsonl(directory / "trend_features.jsonl", [trend])
    roles, updates, deltas = _write_review_inputs(directory)
    export_review_queue(
        directory / "review_queue.csv",
        emerging_roles_path=roles,
        job_skill_updates_path=updates,
        kg_link_delta_path=deltas,
    )


def test_bundle_has_contract_hashes_schemas_and_checksum(tmp_path: Path):
    source = tmp_path / "artifacts"
    _write_bundle_inputs(source)
    result = build_handoff_bundle(
        source,
        tmp_path / "delivery",
        run_id="run-handoff",
        created_at=NOW,
        model_ids={"extraction": "qwen-flash"},
        prompt_versions={"extraction": "jobtrend_extraction_v1"},
    )
    handoff = Path(result.handoff_dir)
    assert all((handoff / name).is_file() for name in REQUIRED_HANDOFF_FILES)
    assert (handoff / "schemas" / "emerging_role_v1.schema.json").is_file()
    assert (handoff / "LOCAL_VALIDATION.json").is_file()
    readme = (handoff / "README.md").read_text(encoding="utf-8")
    assert "3 分钟安装和离线演示" in readme
    assert "统一文档 1" in readme
    manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
    records = {item["path"]: item for item in manifest["output_artifacts"]}
    for name in REQUIRED_DATA_FILES:
        assert records[name]["sha256"] == sha256_file(handoff / name)
        expected_records = 3 if name == "review_queue.csv" else 1
        assert records[name]["records"] == expected_records
    assert records["README.md"]["sha256"] == sha256_file(handoff / "README.md")
    assert records["README.md"]["records"] is None
    assert manifest["run_id"] == "run-handoff"
    archive = Path(result.archive_path)
    assert sha256_file(archive) == result.archive_sha256
    assert Path(result.checksum_path).read_text().startswith(result.archive_sha256)


def test_bundle_source_snapshot_excludes_private_directories(tmp_path: Path):
    source = tmp_path / "artifacts"
    _write_bundle_inputs(source)
    selected = tmp_path / "data"
    snapshot = selected / "real_eval" / "snapshots" / "2026-08-08"
    (snapshot / "shareable").mkdir(parents=True)
    (snapshot / "private").mkdir()
    (snapshot / "annotations").mkdir()
    (selected / "generated.egg-info").mkdir()
    (snapshot / "shareable" / "index.json").write_text(
        '{"redistribution_allowed": false}', encoding="utf-8"
    )
    (snapshot / "private" / "jobs.jsonl").write_text(
        '{"jd_text": "source-reference-only full text"}\n', encoding="utf-8"
    )
    (snapshot / "annotations" / "gold.jsonl").write_text(
        '{"notes": "blind answer and quoted source text"}\n', encoding="utf-8"
    )
    (selected / "generated.egg-info" / "PKG-INFO").write_text(
        "generated build metadata", encoding="utf-8"
    )

    result = build_handoff_bundle(
        source,
        tmp_path / "delivery",
        run_id="run-private-boundary",
        created_at=NOW,
        source_paths=[selected],
    )
    handoff_source = Path(result.handoff_dir) / "source" / "data"
    assert (
        handoff_source / "real_eval" / "snapshots" / "2026-08-08" / "shareable" / "index.json"
    ).is_file()
    assert not any(path.name == "private" for path in handoff_source.rglob("private"))
    assert not any(path.name == "annotations" for path in handoff_source.rglob("annotations"))
    assert not any(path.name == "jobs.jsonl" for path in handoff_source.rglob("*"))
    assert not any(path.name == "gold.jsonl" for path in handoff_source.rglob("*"))
    assert not any(path.name.endswith(".egg-info") for path in handoff_source.rglob("*"))

    for index, sensitive_source in enumerate(
        (snapshot / "private", snapshot / "private" / "jobs.jsonl", snapshot / "annotations"),
        start=1,
    ):
        with pytest.raises(ValueError, match="sensitive source selection"):
            build_handoff_bundle(
                source,
                tmp_path / f"blocked-delivery-{index}",
                run_id=f"run-blocked-{index}",
                created_at=NOW,
                source_paths=[sensitive_source],
            )


def test_bundle_rejects_unredacted_reference_only_documents(tmp_path: Path):
    source = tmp_path / "artifacts"
    _write_bundle_inputs(source)
    rows = list(read_jsonl(source / "external_documents.jsonl"))
    rows[0]["license"] = "source-reference-only"
    write_jsonl(source / "external_documents.jsonl", rows)

    with pytest.raises(ValueError, match="source-reference-only document text"):
        build_handoff_bundle(
            source,
            tmp_path / "delivery",
            run_id="run-reference-only",
            created_at=NOW,
        )


def test_bundle_allows_redacted_reference_with_short_located_excerpt(tmp_path: Path):
    source = tmp_path / "artifacts"
    _write_bundle_inputs(source)
    documents = list(read_jsonl(source / "external_documents.jsonl"))
    documents[0]["license"] = "source-reference-only"
    documents[0]["text"] = ""
    write_jsonl(source / "external_documents.jsonl", documents)

    result = build_handoff_bundle(
        source,
        tmp_path / "delivery",
        run_id="run-redacted-reference",
        created_at=NOW,
    )
    assert Path(result.archive_path).is_file()


def test_bundle_rejects_oversized_reference_only_excerpt(tmp_path: Path):
    source = tmp_path / "artifacts"
    _write_bundle_inputs(source)
    documents = list(read_jsonl(source / "external_documents.jsonl"))
    documents[0]["license"] = "source-reference-only"
    documents[0]["text"] = ""
    write_jsonl(source / "external_documents.jsonl", documents)
    evidence = list(read_jsonl(source / "evidence.jsonl"))
    evidence[0]["text"] = "证" * 301
    evidence[0]["char_end"] = 301
    write_jsonl(source / "evidence.jsonl", evidence)

    with pytest.raises(ValueError, match="evidence exceeds the reviewed excerpt allowance"):
        build_handoff_bundle(
            source,
            tmp_path / "delivery",
            run_id="run-oversized-reference",
            created_at=NOW,
        )


@pytest.mark.parametrize(
    "payload",
    [
        "DASHSCOPE" + "_API_KEY=sk-" + "this-is-a-real-looking-key",
        "workspace=/" + "Users/alice/private-project/data.jsonl",
    ],
)
def test_handoff_rejects_secrets_and_local_paths(tmp_path: Path, payload: str):
    suspect = tmp_path / "suspect.txt"
    suspect.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        assert_safe_for_handoff(suspect)


def test_handoff_rejects_model_weights(tmp_path: Path):
    weight = tmp_path / "model.safetensors"
    weight.write_bytes(b"not really a model")
    with pytest.raises(ValueError, match="model weight"):
        assert_safe_for_handoff(weight)
