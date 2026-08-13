from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest
import yaml

from trend_discovery.exporter import REQUIRED_HANDOFF_FILES


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_team_delivery.py"
_SPEC = importlib.util.spec_from_file_location("build_team_delivery", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build_team_delivery = _MODULE.build_team_delivery


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _component(root: Path) -> Path:
    component = root / "component-handoff"
    component.mkdir()
    for name in REQUIRED_HANDOFF_FILES:
        (component / name).write_text("{}\n", encoding="utf-8")
    (component / "LOCAL_VALIDATION.json").write_text('{"valid": true}\n', encoding="utf-8")
    (component / "source").mkdir()
    (component / "source" / "README.md").write_text("safe component\n", encoding="utf-8")
    (component / "dist").mkdir()
    # A wheel is a ZIP file.  The safety scanner accepts this minimal fixture.
    import zipfile

    with zipfile.ZipFile(component / "dist" / "trend_discovery_service-0.1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("trend_discovery/__init__.py", '__version__ = "0.1.0"\n')
    return component


def _snapshot(root: Path) -> Path:
    snapshot = root / "2026-08-08"
    sources = ["baidu", "huawei", "meituan", "tencent", "xiaomi"]
    all_rows: list[dict[str, object]] = []
    for source in sources:
        rows: list[dict[str, object]] = []
        for index in range(28):
            text = f"岗位职责：负责{source}大模型系统研发 {index}\n岗位要求：熟悉 Python 和模型训练"
            rows.append(
                {
                    "document_id": f"eval-doc:{source}-{index}",
                    "source_id": source,
                    "external_id": f"{source}-{index}",
                    "job_title": "大模型工程师",
                    "company_name": source,
                    "responsibilities": f"负责{source}大模型系统研发 {index}",
                    "requirements": "熟悉 Python 和模型训练",
                    "jd_text": text,
                    "content_sha256": _sha256_text(text),
                    "redistribution_allowed": False,
                }
            )
        _write_jsonl(snapshot / "private" / "jobs" / f"{source}.jsonl", rows)
        all_rows.extend(rows)
    _write_jsonl(snapshot / "private" / "jobs.full.jsonl", all_rows)

    manifest = {
        "schema_version": "source_manifest_v1",
        "sources": [
            {
                "source_id": f"{source}-careers-2026-08-08",
                "source_type": "job",
                "input": f"jobs/{source}.jsonl",
                "input_format": "jsonl",
                "source_name": source,
                "license": "source-reference-only",
            }
            for source in sources
        ],
    }
    (snapshot / "private" / "sources.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    # These must never be copied by the explicit allow-list.
    (snapshot / "private" / "raw").mkdir()
    (snapshot / "private" / "raw" / "response.json").write_text(
        '{"body": "raw response"}\n', encoding="utf-8"
    )
    (snapshot / "private" / "reports").mkdir()
    (snapshot / "private" / "reports" / "industry-report.pdf").write_bytes(b"%PDF-full-report")

    annotations = snapshot / "annotations"
    annotations.mkdir()
    for name in (
        "dedup_pairs_A.csv",
        "dedup_pairs_B.csv",
        "jd_annotations_A.jsonl",
        "jd_annotations_B.jsonl",
        "rag_queries_A.jsonl",
        "rag_queries_B.jsonl",
    ):
        (annotations / name).write_text("header\n", encoding="utf-8")
    (annotations / "split_manifest.json").write_text('{"gold_status": "unlabelled"}\n', encoding="utf-8")

    shareable = snapshot / "shareable"
    shareable.mkdir()
    _write_jsonl(shareable / "jobs.reference.jsonl", [{"document_id": row["document_id"]} for row in all_rows])
    _write_jsonl(shareable / "collection_snapshots.jsonl", [{"snapshot_week": "2026-W32"}])
    (shareable / "evaluation_readiness.json").write_text('{"status": "structural_pass"}\n', encoding="utf-8")

    report = {
        "schema_version": "public_eval_collection_report_v1",
        "snapshot_date": "2026-08-08",
        "snapshot_week": "2026-W32",
        "record_count": 140,
        "company_count": 5,
        "source_counts": {source: 28 for source in sources},
        "paths": {"source_manifest": "private/sources.yaml", "private_jobs": "private/jobs.full.jsonl"},
    }
    (snapshot / "collection_report.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    return snapshot


def _analysis(root: Path) -> Path:
    analysis = root / "analysis"
    analysis.mkdir()
    counts = {
        "external_documents.jsonl": 140,
        "evidence.jsonl": 144,
        "ingest_runs.jsonl": 1,
        "job_observations.jsonl": 140,
        "trend_features.jsonl": 110,
        "emerging_roles.jsonl": 0,
        "job_skill_updates.jsonl": 0,
        "kg_link_delta.jsonl": 0,
        "rag_contexts.jsonl": 0,
    }
    for name, count in counts.items():
        rows = [{"record": index, "artifact": name} for index in range(count)]
        if name in {"external_documents.jsonl", "evidence.jsonl"}:
            for row in rows:
                row["source_type"] = "job"
        _write_jsonl(analysis / name, rows)
    (analysis / "review_queue.csv").write_text("object_type,object_id\n", encoding="utf-8")
    (analysis / "manifest.json").write_text('{"status": "completed"}\n', encoding="utf-8")
    (analysis / "quality_report.json").write_text('{"status": "valid"}\n', encoding="utf-8")
    # These siblings must not be swept into the package.
    (analysis / "warehouse.duckdb").write_bytes(b"not-public")
    (analysis / "qdrant").mkdir()
    (analysis / "qdrant" / "collection.sqlite").write_bytes(b"not-public")
    return analysis


def _historical_jd(root: Path) -> Path:
    path = root / "jd_raw.jsonl"
    contact_indices = {1000, 1001, 1002, 5980, 5981}
    with path.open("w", encoding="utf-8") as handle:
        for index in range(10_515):
            text = f"负责历史岗位研发 {index}"
            if index in contact_indices:
                text += f" 联系邮箱 person{index}@example.com"
            row = {
                "source_type": "job_platform",
                "source_name": "zhaopin",
                "job_id": f"history-{index}",
                "job_title": "算法工程师",
                "company_name": f"company-{index % 4_980}",
                "publish_date": "2025-01-01 00:00:00" if index == 0 else "2026-07-01 00:00:00",
                "scrape_time": "2026-07-06T00:00:00Z" if index == 0 else "2026-07-14T00:00:00Z",
                "jd_text": text,
                "responsibilities": [text],
                "requirements": ["熟悉 Python"],
                "provenance_marker": {"page": index // 20, "source_row": index},
            }
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (root / "jd_raw_summary.json").write_text('{"must_not_be_copied": true}\n', encoding="utf-8")
    (root / "jd_raw.csv").write_text("must,not,be,copied\n", encoding="utf-8")
    return path


def _extract(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(destination, filter="data")
    roots = [path for path in destination.iterdir() if path.is_dir()]
    assert len(roots) == 1
    return roots[0]


def test_team_delivery_contains_internal_dataset_and_complete_hash_manifest(tmp_path: Path) -> None:
    component = _component(tmp_path)
    snapshot = _snapshot(tmp_path)
    analysis = _analysis(tmp_path)
    first = build_team_delivery(
        component, snapshot, tmp_path / "out-a", analysis_dir=analysis
    )
    second = build_team_delivery(
        component, snapshot, tmp_path / "out-b", analysis_dir=analysis
    )
    archive = Path(first["archive_path"])

    assert archive.read_bytes() == Path(second["archive_path"]).read_bytes()
    assert first["classification"] == "INTERNAL-ONLY"
    assert first["record_count"] == 140
    digest, filename = Path(first["checksum_path"]).read_text(encoding="ascii").split()
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert filename == archive.name

    root = _extract(archive, tmp_path / "extracted")
    dataset = root / "datasets" / "real_eval_2026-08-08"
    assert (root / "README.md").is_file()
    assert "INTERNAL-ONLY" in (root / "README.md").read_text(encoding="utf-8")
    assert (root / "component" / "LOCAL_VALIDATION.json").is_file()
    assert (dataset / "private" / "jobs.full.jsonl").is_file()
    assert len(list((dataset / "private" / "jobs").glob("*.jsonl"))) == 5
    assert (dataset / "sources.yaml").is_file()
    assert not (dataset / "private" / "sources.yaml").exists()
    assert not (dataset / "private" / "raw").exists()
    assert not list(dataset.rglob("*.pdf"))
    assert not list(dataset.rglob("*.docx"))
    pipeline = dataset / "pipeline_outputs"
    assert (pipeline / "job_observations.jsonl").is_file()
    assert (pipeline / "ingest_runs.jsonl").is_file()
    assert not (pipeline / "warehouse.duckdb").exists()
    assert not (pipeline / "qdrant").exists()
    card = (dataset / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "140 个岗位观测" in card
    assert "110 条趋势特征" in card
    assert "0 个新岗位候选" in card

    relocated = yaml.safe_load((dataset / "sources.yaml").read_text(encoding="utf-8"))
    assert all(source["input"].startswith("private/jobs/") for source in relocated["sources"])
    report = json.loads((dataset / "collection_report.json").read_text(encoding="utf-8"))
    assert report["paths"]["source_manifest"] == "sources.yaml"
    assert report["team_delivery"]["raw_http_responses_included"] is False

    listed: dict[str, str] = {}
    for line in (root / "MANIFEST.sha256").read_text(encoding="ascii").splitlines():
        file_digest, relative = line.split("  ", 1)
        listed[relative] = file_digest
    actual = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    assert listed == actual


def test_team_delivery_refuses_overwrite_and_contact_data(tmp_path: Path) -> None:
    component = _component(tmp_path)
    snapshot = _snapshot(tmp_path)
    output = tmp_path / "out"
    build_team_delivery(component, snapshot, output)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_team_delivery(component, snapshot, output)

    bad = _snapshot(tmp_path / "bad-contact")
    rows = [json.loads(line) for line in (bad / "private" / "jobs.full.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[0]["requirements"] += " 联系邮箱 eval@example.com"
    rows[0]["jd_text"] += "\n联系邮箱 eval@example.com"
    rows[0]["content_sha256"] = _sha256_text(str(rows[0]["jd_text"]))
    _write_jsonl(bad / "private" / "jobs.full.jsonl", rows)
    source_file = bad / "private" / "jobs" / f"{rows[0]['source_id']}.jsonl"
    source_rows = [json.loads(line) for line in source_file.read_text(encoding="utf-8").splitlines()]
    source_rows[0] = rows[0]
    _write_jsonl(source_file, source_rows)
    with pytest.raises(ValueError, match="email or phone"):
        build_team_delivery(component, bad, tmp_path / "bad-contact-out")


@pytest.mark.parametrize(
    "payload, expected",
    [
        ('{"notes": "__ROOT__Users/alice/private/file"}\n', "local user absolute path"),
        ('{"__KEY__": "abcdefghijklmnopqrstuvwxyz"}\n', "possible API credential"),
    ],
)
def test_team_delivery_rejects_local_paths_and_api_keys(
    tmp_path: Path, payload: str, expected: str
) -> None:
    component = _component(tmp_path)
    snapshot = _snapshot(tmp_path)
    rendered = payload.replace("__ROOT__", "/").replace("__KEY__", "api_key")
    (snapshot / "annotations" / "unsafe.jsonl").write_text(rendered, encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        build_team_delivery(component, snapshot, tmp_path / "out")


def test_team_delivery_rejects_report_fulltext_in_shareable(tmp_path: Path) -> None:
    component = _component(tmp_path)
    snapshot = _snapshot(tmp_path)
    (snapshot / "shareable" / "report.json").write_text(
        '{"title": "industry report", "text": "full report body"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="full-text keys"):
        build_team_delivery(component, snapshot, tmp_path / "out")


def test_team_delivery_sanitizes_historical_jd_and_records_provenance(tmp_path: Path) -> None:
    component = _component(tmp_path)
    snapshot = _snapshot(tmp_path)
    historical = _historical_jd(tmp_path)
    original_sha = hashlib.sha256(historical.read_bytes()).hexdigest()
    result = build_team_delivery(
        component,
        snapshot,
        tmp_path / "out",
        historical_jd=historical,
    )
    assert result["historical_record_count"] == 10_510

    root = _extract(Path(result["archive_path"]), tmp_path / "historical-extracted")
    dataset = root / "datasets" / "historical_zhaopin"
    sanitized = dataset / "jd_raw.sanitized.jsonl"
    rows = [json.loads(line) for line in sanitized.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10_510
    assert all("@example.com" not in row["jd_text"] for row in rows)
    assert rows[0]["provenance_marker"] == {"page": 0, "source_row": 0}

    summary = json.loads((dataset / "summary.json").read_text(encoding="utf-8"))
    assert summary["input_sha256"] == original_sha
    assert summary["output_sha256"] == hashlib.sha256(sanitized.read_bytes()).hexdigest()
    assert summary["input_record_count"] == 10_515
    assert summary["output_record_count"] == 10_510
    assert summary["dropped_contact_record_count"] == 5
    assert summary["dropped_job_ids"] == [
        "history-1000",
        "history-1001",
        "history-1002",
        "history-5980",
        "history-5981",
    ]
    assert summary["input_company_count"] == 4_980
    assert summary["output_company_count"] == 4_978
    assert "/Users/" not in json.dumps(summary)

    source_manifest = yaml.safe_load((dataset / "sources.yaml").read_text(encoding="utf-8"))
    source = source_manifest["sources"][0]
    assert source["input"] == "jd_raw.sanitized.jsonl"
    assert source["source_name"] == "zhaopin"
    assert source["license"] == "source-reference-only/team-internal"
    assert not (dataset / "jd_raw_summary.json").exists()
    assert not (dataset / "jd_raw.csv").exists()
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "../../datasets/historical_zhaopin/sources.yaml" in readme
    assert "10510 条" in readme
