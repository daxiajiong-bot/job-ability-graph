from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import yaml

from trend_discovery.ingest import load_source_manifest
from trend_discovery.io_utils import read_jsonl
from trend_discovery.public_eval import (
    collect_public_evaluation_snapshot,
    summarize_authoritative_corpus,
    validate_evaluation_snapshot,
)
from trend_discovery.schemas import Evidence, ExternalDocument
from trend_discovery.warehouse import Warehouse


RESPONSIBILITY = "负责大模型训练、检索增强生成和智能体应用研发，持续优化模型效果、服务性能与工程稳定性。"
REQUIREMENT = "熟悉 Python、PyTorch、Transformer 和分布式训练，有完整人工智能项目经验。"


def _json_response(request: httpx.Request, value: object) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        headers={"Content-Type": "application/json"},
        content=json.dumps(value, ensure_ascii=False).encode(),
    )


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(
            200,
            request=request,
            headers={"Content-Type": "text/plain"},
            text="User-agent: *\nAllow: /\n",
        )
    if request.url.host == "careers.tencent.com" and path.endswith("/Query"):
        return _json_response(
            request,
            {
                "Code": 200,
                "Data": {
                    "Count": 1,
                    "Posts": [
                        {
                            "PostId": "tx-1",
                            "RecruitPostName": "大模型工程师",
                            "CountryName": "中国",
                            "LocationName": "深圳",
                            "Responsibility": RESPONSIBILITY,
                        }
                    ],
                },
            },
        )
    if request.url.host == "careers.tencent.com" and path.endswith("/ByPostId"):
        return _json_response(
            request,
            {
                "Code": 200,
                "Data": {
                    "PostId": "tx-1",
                    "RecruitPostName": "大模型工程师",
                    "LocationName": "深圳",
                    "Responsibility": RESPONSIBILITY,
                    "Requirement": REQUIREMENT,
                    "LastUpdateTime": "2026年08月01日",
                },
            },
        )
    if request.url.host == "zhaopin.meituan.com" and path.endswith("/getJobList"):
        return _json_response(
            request,
            {
                "status": 0,
                "data": {
                    "page": {"totalCount": 1},
                    "list": [
                        {
                            "jobUnionId": "mt-1",
                            "name": "大模型算法工程师",
                            "cityList": [{"name": "北京市"}],
                            "jobDuty": RESPONSIBILITY,
                            "jobRequirement": REQUIREMENT,
                            "refreshTime": 1785513600000,
                        }
                    ],
                },
            },
        )
    if request.url.host == "hr.xiaomi.com" and path.endswith("/searchJobPage"):
        return _json_response(
            request,
            {
                "code": 0,
                "data": {
                    "total": 1,
                    "list": [
                        {
                            "jobPostId": "mi-1",
                            "title": "大模型应用工程师",
                            "cityZhNames": ["上海"],
                            "description": RESPONSIBILITY,
                            "requirement": REQUIREMENT,
                            "publishTime": "2026-08-01",
                            "type": 1,
                            "url": "https://xiaomi.jobs.f.mioffice.cn/experienced/position/mi-1/detail",
                        }
                    ],
                },
            },
        )
    if request.url.host == "talent.baidu.com" and path.endswith("/getPostListNew"):
        return _json_response(
            request,
            {
                "status": "ok",
                "data": {
                    "total": "1",
                    "list": [
                        {
                            "postId": "bd-1",
                            "name": "大模型研发工程师",
                            "workPlace": "北京市",
                            "workContent": RESPONSIBILITY,
                            "serviceCondition": REQUIREMENT,
                            "publishDate": "2026-08-01",
                            "updateDate": "2026-08-02",
                        }
                    ],
                },
            },
        )
    if request.url.host == "career.huawei.com" and path.endswith("social-recruitment-ai.html"):
        return httpx.Response(
            200,
            request=request,
            headers={"Content-Type": "text/html"},
            text=(
                '<a href="/reccampportal/portal5/social-recruitment-detail.html?'
                'jobId=hw-1&amp;dataSource=1">大模型架构师</a>'
            ),
        )
    if request.url.host == "career.huawei.com" and path.endswith("/getJobDetail/newHr"):
        return _json_response(
            request,
            {
                "jobId": "hw-1",
                "jobname": "大模型架构师",
                "jobArea": "中国/北京",
                "mainBusiness": RESPONSIBILITY,
                "jobRequire": REQUIREMENT,
                "issuanceStartDate": "2026-08-01T08:00:00.000+0800",
                "lastUpdateDate": "2026-08-02T08:00:00.000+0800",
                "dataSource": "1",
            },
        )
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


def test_public_eval_collection_is_audited_and_ingestable(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=True)
    report = collect_public_evaluation_snapshot(
        tmp_path,
        snapshot_date=date(2026, 8, 8),
        quotas={source: 1 for source in ("tencent", "meituan", "xiaomi", "baidu", "huawei")},
        delay_seconds=0,
        client=client,
    )
    root = tmp_path / "2026-08-08"

    assert report["record_count"] == 5
    assert report["company_count"] == 5
    assert report["records_with_responsibilities"] == 5
    assert report["records_with_requirements"] == 5
    assert report["trend_validity"]["valid_for_temporal_trend_eval"] is False
    assert report["annotation"] == {
        "calibration_count": 5,
        "test_count": 0,
        "gold_status": "unlabelled",
        "dedup_pair_count": 10,
        "rag_query_template_count_per_annotator": 60,
    }

    full = list(read_jsonl(root / "private" / "jobs.full.jsonl"))
    references = list(read_jsonl(root / "shareable" / "jobs.reference.jsonl"))
    snapshots = list(read_jsonl(root / "shareable" / "collection_snapshots.jsonl"))
    assert len(full) == len(references) == len(snapshots) == 5
    assert all(row["redistribution_allowed"] is False for row in full)
    assert all("jd_text" not in row for row in references)
    assert all(row["valid_for_trend"] is False for row in snapshots)
    assert len(list((root / "private" / "raw").glob("*/*"))) == report["http_request_count"]
    assert len((root / "annotations" / "dedup_pairs_A.csv").read_text().splitlines()) == 11
    assert len(list(read_jsonl(root / "annotations" / "rag_queries_A.jsonl"))) == 60

    manifest = load_source_manifest(root / "private" / "sources.yaml")
    assert len(manifest.sources) == 5
    assert {source.publisher for source in manifest.sources} == {"腾讯", "美团", "小米", "百度", "华为"}
    payload = yaml.safe_load((root / "private" / "sources.yaml").read_text(encoding="utf-8"))
    assert all(source["metadata"]["redistribution_allowed"] is False for source in payload["sources"])

    readiness = validate_evaluation_snapshot(root)
    # The tiny fixture intentionally fails only the real-dataset volume gates;
    # all integrity checks below them still run and are visible.
    assert readiness["status"] == "failed"
    checks = {row["name"]: row["passed"] for row in readiness["checks"]}
    assert checks["minimum_records"] is False
    assert checks["minimum_companies"] is True
    assert checks["content_sha256"] is True
    assert checks["dual_annotation_coverage"] is True
    assert readiness["gold_evaluation"]["jd_field_f1"] is None


def test_real_snapshot_refuses_overwrite(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=True)
    kwargs = {
        "snapshot_date": date(2026, 8, 8),
        "quotas": {source: 1 for source in ("tencent", "meituan", "xiaomi", "baidu", "huawei")},
        "delay_seconds": 0,
        "client": client,
    }
    collect_public_evaluation_snapshot(tmp_path, **kwargs)
    try:
        collect_public_evaluation_snapshot(tmp_path, **kwargs)
    except FileExistsError as exc:
        assert "already finalized" in str(exc)
    else:  # pragma: no cover - explicit assertion message is clearer here
        raise AssertionError("a finalized real snapshot must be append-only")


def test_authoritative_summary_is_reference_only(tmp_path: Path) -> None:
    warehouse = Warehouse(tmp_path / "warehouse")
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    documents = [
        ExternalDocument(
            document_id="doc-policy",
            source_type="policy",
            source_name="official",
            title="人工智能政策",
            text="人工智能岗位能力发展。" * 20,
            raw_sha256="a" * 64,
            parser_version="test",
            publisher="权威机构",
            uri="https://example.gov.cn/policy",
            collected_at=now,
            license="source-reference-only",
            metadata={
                "source_id": "policy-1",
                "parser_backend": "test",
                "detected_format": "html",
                "rights": {"redistribution_allowed": False, "fulltext_in_handoff": False},
            },
        ),
        ExternalDocument(
            document_id="doc-report",
            source_type="industry_report",
            source_name="official",
            title="人工智能报告",
            text="",
            raw_sha256="b" * 64,
            parser_version="test",
            publisher="权威机构",
            uri="https://example.org/report",
            collected_at=now,
            license="source-reference-only",
            metadata={"source_id": "report-1", "rights": {"redistribution_allowed": False}},
        ),
    ]
    evidence = [
        Evidence(
            evidence_id="ev-policy",
            document_id="doc-policy",
            source_type="policy",
            text="人工智能岗位能力发展。",
            text_sha256="c" * 64,
            char_start=0,
            char_end=11,
        )
    ]
    warehouse.upsert(documents, evidence)

    report = summarize_authoritative_corpus(warehouse.root, tmp_path / "shareable")
    references = list(read_jsonl(tmp_path / "shareable" / "authoritative_documents.reference.jsonl"))
    assert report["document_count"] == 2
    assert report["evidence_ready_count"] == 1
    assert report["metadata_only_source_ids"] == ["report-1"]
    assert all("text" not in row and "evidence_text" not in row for row in references)
    assert {row["source_id"] for row in references} == {"policy-1", "report-1"}
