#!/usr/bin/env python3
"""Build the INTERNAL-ONLY team delivery around a validated component handoff.

The public/component exporter deliberately excludes source-reference-only job
text and annotation answers.  This script is a separate, explicit boundary for
sharing those evaluation materials *inside the team*.  It copies only a small
allow-list from one real snapshot and never copies raw HTTP responses or full
policy/report files.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping

import yaml

from trend_discovery.exporter import REQUIRED_HANDOFF_FILES, assert_safe_for_handoff


EXPECTED_RECORD_COUNT = 140
MINIMUM_COMPANY_COUNT = 5
EXPECTED_HISTORICAL_INPUT_COUNT = 10_515
EXPECTED_HISTORICAL_DROPPED_CONTACT_COUNT = 5
EXPECTED_HISTORICAL_OUTPUT_COUNT = 10_510
EXPECTED_HISTORICAL_INPUT_COMPANY_COUNT = 4_980
EXPECTED_HISTORICAL_OUTPUT_COMPANY_COUNT = 4_978
PIPELINE_OUTPUT_FILES = (
    "external_documents.jsonl",
    "evidence.jsonl",
    "ingest_runs.jsonl",
    "job_observations.jsonl",
    "trend_features.jsonl",
    "emerging_roles.jsonl",
    "job_skill_updates.jsonl",
    "kg_link_delta.jsonl",
    "review_queue.csv",
    "manifest.json",
    "quality_report.json",
    "rag_contexts.jsonl",
)
CORE_ANNOTATION_FILES = {
    "dedup_pairs_A.csv",
    "dedup_pairs_B.csv",
    "jd_annotations_A.jsonl",
    "jd_annotations_B.jsonl",
    "rag_queries_A.jsonl",
    "rag_queries_B.jsonl",
    "split_manifest.json",
}
REQUIRED_SHAREABLE_FILES = {
    "collection_snapshots.jsonl",
    "evaluation_readiness.json",
    "jobs.reference.jsonl",
}
ALLOWED_ANNOTATION_SUFFIXES = {".csv", ".json", ".jsonl", ".md"}
ALLOWED_SHAREABLE_SUFFIXES = {".csv", ".json", ".jsonl", ".md"}
FORBIDDEN_DOCUMENT_SUFFIXES = {
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
}
FORBIDDEN_SHAREABLE_KEYS = {
    "body",
    "document_text",
    "evidence_text",
    "full_text",
    "jd_text",
    "raw_text",
    "requirements",
    "responsibilities",
    "text",
}
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:1[3-9]\d{9}|(?:\+?86[- ]?)?0\d{2,3}[- ]?\d{7,8})(?!\d)"
)
LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|"
    r"[A-Za-z]:\\Users\\[^\\\s]+\\)"
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization\s*:\s*bearer)\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"(?i)[\"']?(?:DASHSCOPE_API_KEY|api[_-]?key)[\"']?\s*[=:]\s*[\"']?"
        r"(?!\$\{|<|YOUR_|REDACTED|NONE\b|NULL\b)[A-Za-z0-9._-]{12,}"
    ),
)
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SNAPSHOT_DATE_PATTERN = re.compile(r"20\d{2}-\d{2}-\d{2}\Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_team_safe(path: Path) -> None:
    """Apply the public exporter scan plus JSON-aware secret/path checks."""

    assert_safe_for_handoff(path)
    if path.stat().st_size > 10 * 1024 * 1024:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    if LOCAL_PATH_PATTERN.search(text):
        raise ValueError(f"{path}: local user absolute path detected")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"{path}: possible API credential detected")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"{label}: unsafe relative path {value!r}")
    return path


def _validate_bundle_name(value: str) -> str:
    if not SAFE_NAME_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise ValueError("bundle_name must be one safe ASCII directory name")
    return value


def _validate_component(component: Path) -> str:
    if not component.is_dir():
        raise FileNotFoundError(f"component handoff directory not found: {component}")
    required_component_files = (*REQUIRED_HANDOFF_FILES, "LOCAL_VALIDATION.json")
    missing = [name for name in required_component_files if not (component / name).is_file()]
    if missing:
        raise FileNotFoundError(f"component handoff is missing required files: {missing}")
    validation = _read_json(component / "LOCAL_VALIDATION.json")
    if validation.get("valid") is not True:
        raise ValueError("component LOCAL_VALIDATION.json is not valid=true")
    wheels = sorted((component / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("component must contain exactly one wheel under dist/")
    if not (component / "source").is_dir():
        raise FileNotFoundError("component source/ directory is missing")

    for candidate in sorted(component.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"component symlinks are not allowed: {candidate}")
        if candidate.is_file():
            _assert_team_safe(candidate)
    return wheels[0].name


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_contact_free(rows: Iterable[Mapping[str, Any]]) -> None:
    hits: list[str] = []
    for index, row in enumerate(rows, start=1):
        text = "\n".join(
            str(row.get(field) or "")
            for field in ("job_title", "responsibilities", "requirements", "jd_text")
        )
        if EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text):
            hits.append(str(row.get("document_id") or f"row-{index}"))
    if hits:
        raise ValueError(f"job dataset contains email or phone contact data: {hits[:5]}")


def _validate_shareable_json_has_no_full_text(path: Path) -> None:
    values: list[Any]
    if path.suffix == ".jsonl":
        values = list(_read_jsonl(path))
    elif path.suffix == ".json":
        values = [json.loads(path.read_text(encoding="utf-8"))]
    else:
        return

    def walk(value: Any, location: str) -> None:
        if isinstance(value, dict):
            forbidden = FORBIDDEN_SHAREABLE_KEYS & set(map(str, value))
            if forbidden:
                raise ValueError(
                    f"{path}:{location}: shareable metadata contains full-text keys "
                    f"{sorted(forbidden)}"
                )
            for key, child in value.items():
                walk(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")

    for index, value in enumerate(values):
        walk(value, f"record[{index}]")


def _validate_snapshot(snapshot: Path) -> dict[str, Any]:
    required = {
        snapshot / "private" / "jobs.full.jsonl",
        snapshot / "private" / "sources.yaml",
        snapshot / "collection_report.json",
    }
    missing = sorted(str(path) for path in required if not path.is_file())
    if missing:
        raise FileNotFoundError(f"snapshot is missing required files: {missing}")
    for directory in (snapshot / "private" / "jobs", snapshot / "annotations", snapshot / "shareable"):
        if not directory.is_dir():
            raise FileNotFoundError(f"snapshot directory is missing: {directory}")

    report = _read_json(snapshot / "collection_report.json")
    snapshot_date = str(report.get("snapshot_date") or snapshot.name)
    if not SNAPSHOT_DATE_PATTERN.fullmatch(snapshot_date):
        raise ValueError("snapshot date must be YYYY-MM-DD")
    if report.get("record_count") != EXPECTED_RECORD_COUNT:
        raise ValueError(
            f"collection_report record_count must be {EXPECTED_RECORD_COUNT}, "
            f"got {report.get('record_count')!r}"
        )

    full_path = snapshot / "private" / "jobs.full.jsonl"
    rows = list(_read_jsonl(full_path))
    if len(rows) != EXPECTED_RECORD_COUNT:
        raise ValueError(f"jobs.full.jsonl must contain exactly {EXPECTED_RECORD_COUNT} records")
    required_fields = {
        "company_name",
        "content_sha256",
        "document_id",
        "external_id",
        "jd_text",
        "job_title",
        "requirements",
        "responsibilities",
        "source_id",
    }
    missing_fields: list[str] = []
    bad_hashes: list[str] = []
    identifiers: list[tuple[str, str]] = []
    for index, row in enumerate(rows, start=1):
        missing = sorted(required_fields - set(row))
        if missing:
            missing_fields.append(f"row-{index}:{','.join(missing)}")
            continue
        identifiers.append((str(row["source_id"]), str(row["external_id"])))
        actual = hashlib.sha256(str(row["jd_text"]).encode("utf-8")).hexdigest()
        if actual != row["content_sha256"]:
            bad_hashes.append(str(row["document_id"]))
        if row.get("redistribution_allowed") is not False:
            raise ValueError("all internal JD rows must remain redistribution_allowed=false")
    if missing_fields:
        raise ValueError(f"job records are missing required fields: {missing_fields[:5]}")
    if bad_hashes:
        raise ValueError(f"job content hashes do not match: {bad_hashes[:5]}")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("source_id/external_id pairs must be unique")
    _validate_contact_free(rows)

    company_count = len({str(row["company_name"]) for row in rows})
    if company_count < MINIMUM_COMPANY_COUNT:
        raise ValueError(f"job dataset must contain at least {MINIMUM_COMPANY_COUNT} companies")

    job_files = sorted((snapshot / "private" / "jobs").glob("*.jsonl"))
    if len(job_files) < MINIMUM_COMPANY_COUNT:
        raise ValueError(f"expected at least {MINIMUM_COMPANY_COUNT} per-source job files")
    source_rows = [row for path in job_files for row in _read_jsonl(path)]
    if Counter(map(_row_fingerprint, source_rows)) != Counter(map(_row_fingerprint, rows)):
        raise ValueError("per-source job files do not exactly reconstruct jobs.full.jsonl")

    manifest = yaml.safe_load((snapshot / "private" / "sources.yaml").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise ValueError("private/sources.yaml is not a source_manifest_v1 mapping")
    source_inputs: set[str] = set()
    for source in manifest["sources"]:
        if not isinstance(source, dict) or source.get("source_type") != "job":
            raise ValueError("team evaluation package may contain only job sources")
        relative = _safe_relative_path(str(source.get("input") or ""), label="source input")
        if relative.parts[0] != "jobs" or len(relative.parts) != 2 or relative.suffix != ".jsonl":
            raise ValueError(f"unexpected source input outside jobs/: {relative}")
        source_inputs.add(relative.name)
    if source_inputs != {path.name for path in job_files}:
        raise ValueError("sources.yaml inputs do not match private/jobs/*.jsonl")

    annotation_names = {path.name for path in (snapshot / "annotations").iterdir() if path.is_file()}
    if missing_annotations := sorted(CORE_ANNOTATION_FILES - annotation_names):
        raise FileNotFoundError(f"snapshot is missing annotation templates: {missing_annotations}")
    shareable_names = {path.name for path in (snapshot / "shareable").iterdir() if path.is_file()}
    if missing_shareable := sorted(REQUIRED_SHAREABLE_FILES - shareable_names):
        raise FileNotFoundError(f"snapshot is missing shareable audit files: {missing_shareable}")

    return {
        "snapshot_date": snapshot_date,
        "snapshot_week": report.get("snapshot_week"),
        "record_count": len(rows),
        "company_count": company_count,
        "source_counts": dict(sorted(Counter(str(row["source_id"]) for row in rows).items())),
        "wheel_install_requires_dependencies": True,
    }


def _count_jsonl(path: Path) -> int:
    return sum(1 for _ in _read_jsonl(path))


def _validate_analysis(analysis: Path | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    if not analysis.is_dir():
        raise FileNotFoundError(f"analysis directory not found: {analysis}")
    missing = [name for name in PIPELINE_OUTPUT_FILES if not (analysis / name).is_file()]
    if missing:
        raise FileNotFoundError(f"analysis directory is missing public outputs: {missing}")
    for name in PIPELINE_OUTPUT_FILES:
        path = analysis / name
        if path.is_symlink():
            raise ValueError(f"analysis output symlinks are not allowed: {path}")
        _assert_team_safe(path)

    counts = {
        name.removesuffix(".jsonl"): _count_jsonl(analysis / name)
        for name in PIPELINE_OUTPUT_FILES
        if name.endswith(".jsonl")
    }
    quality = _read_json(analysis / "quality_report.json")
    if quality.get("status") != "valid":
        raise ValueError("analysis quality_report.json must have status=valid")
    expected = {
        "external_documents": 140,
        "job_observations": 140,
        "trend_features": 110,
        "emerging_roles": 0,
        "job_skill_updates": 0,
        "kg_link_delta": 0,
    }
    mismatches = {
        name: {"expected": expected_count, "actual": counts.get(name)}
        for name, expected_count in expected.items()
        if counts.get(name) != expected_count
    }
    if mismatches:
        raise ValueError(f"analysis is not the validated first-week real run: {mismatches}")
    external_documents = list(_read_jsonl(analysis / "external_documents.jsonl"))
    evidence = list(_read_jsonl(analysis / "evidence.jsonl"))
    non_job_documents = [
        str(row.get("document_id") or index)
        for index, row in enumerate(external_documents, start=1)
        if row.get("source_type") != "job"
    ]
    non_job_evidence = [
        str(row.get("evidence_id") or index)
        for index, row in enumerate(evidence, start=1)
        if row.get("source_type") != "job"
    ]
    if non_job_documents or non_job_evidence:
        raise ValueError(
            "pipeline_outputs may contain only job documents/evidence; "
            "policy and report full text is excluded"
        )
    return counts


def _scan_historical_line(raw_text: str, contact_text: str, *, line_number: int) -> bool:
    if LOCAL_PATH_PATTERN.search(raw_text):
        raise ValueError(f"historical JD line {line_number}: local user absolute path detected")
    for pattern in SECRET_PATTERNS:
        if pattern.search(raw_text):
            raise ValueError(f"historical JD line {line_number}: possible API credential detected")
    return bool(EMAIL_PATTERN.search(contact_text) or PHONE_PATTERN.search(contact_text))


def _package_historical_jd(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(f"historical JD JSONL not found: {source}")
    if source.is_symlink():
        raise ValueError(f"historical JD symlinks are not allowed: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    sanitized = destination / "jd_raw.sanitized.jsonl"
    digest = hashlib.sha256()
    input_count = 0
    output_count = 0
    dropped_ids: list[str] = []
    input_companies: set[str] = set()
    retained_companies: set[str] = set()
    source_names: set[str] = set()
    publish_dates: list[str] = []
    scrape_times: list[str] = []

    with source.open("rb") as input_handle, sanitized.open("wb") as output_handle:
        for line_number, raw in enumerate(input_handle, start=1):
            digest.update(raw)
            if not raw.strip():
                continue
            input_count += 1
            try:
                text = raw.decode("utf-8-sig" if line_number == 1 else "utf-8")
                value = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"historical JD line {line_number}: invalid UTF-8 JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"historical JD line {line_number}: expected a JSON object")
            company = str(value.get("company_name") or "").strip()
            if company:
                input_companies.add(company)
            source_name = str(value.get("source_name") or "").casefold()
            if source_name:
                source_names.add(source_name)
            contact_text = "\n".join(
                json.dumps(value.get(field), ensure_ascii=False)
                for field in ("job_title", "responsibilities", "requirements", "jd_text")
            )
            if _scan_historical_line(text, contact_text, line_number=line_number):
                dropped_ids.append(str(value.get("job_id") or f"line-{line_number}"))
                continue
            if company:
                retained_companies.add(company)
            published = str(value.get("publish_date") or "").strip()
            scraped = str(value.get("scrape_time") or "").strip()
            if published:
                publish_dates.append(published)
            if scraped:
                scrape_times.append(scraped)
            output_handle.write(raw if raw.endswith(b"\n") else raw + b"\n")
            output_count += 1

    if input_count != EXPECTED_HISTORICAL_INPUT_COUNT:
        raise ValueError(
            f"historical JD input must contain {EXPECTED_HISTORICAL_INPUT_COUNT} records, "
            f"got {input_count}"
        )
    if len(dropped_ids) != EXPECTED_HISTORICAL_DROPPED_CONTACT_COUNT:
        raise ValueError(
            "historical JD contact filter must drop exactly "
            f"{EXPECTED_HISTORICAL_DROPPED_CONTACT_COUNT} records, got {len(dropped_ids)}"
        )
    if output_count != EXPECTED_HISTORICAL_OUTPUT_COUNT:
        raise ValueError(
            f"historical sanitized output must contain {EXPECTED_HISTORICAL_OUTPUT_COUNT} records"
        )
    if source_names != {"zhaopin"}:
        raise ValueError(f"historical JD must be single-source zhaopin, got {sorted(source_names)}")
    if len(input_companies) != EXPECTED_HISTORICAL_INPUT_COMPANY_COUNT:
        raise ValueError(
            f"historical JD must contain {EXPECTED_HISTORICAL_INPUT_COMPANY_COUNT} input companies, "
            f"got {len(input_companies)}"
        )
    if len(retained_companies) != EXPECTED_HISTORICAL_OUTPUT_COMPANY_COUNT:
        raise ValueError(
            f"historical JD must contain {EXPECTED_HISTORICAL_OUTPUT_COMPANY_COUNT} retained companies, "
            f"got {len(retained_companies)}"
        )

    summary = {
        "schema_version": "jobtrend_historical_jd_summary_v1",
        "classification": "INTERNAL-ONLY",
        "input_artifact": source.name,
        "input_sha256": digest.hexdigest(),
        "output_artifact": sanitized.name,
        "output_sha256": _sha256_file(sanitized),
        "input_record_count": input_count,
        "output_record_count": output_count,
        "dropped_contact_record_count": len(dropped_ids),
        "dropped_job_ids": dropped_ids,
        "input_company_count": len(input_companies),
        "output_company_count": len(retained_companies),
        "source_counts": {"zhaopin": output_count},
        "publish_date_range": {
            "minimum": min(publish_dates) if publish_dates else None,
            "maximum": max(publish_dates) if publish_dates else None,
        },
        "scrape_time_range": {
            "minimum": min(scrape_times) if scrape_times else None,
            "maximum": max(scrape_times) if scrape_times else None,
        },
        "rights": {
            "license": "source-reference-only/team-internal",
            "redistribution_allowed": False,
        },
        "trend_limitations": [
            "All retained records come from the single zhaopin source.",
            "Old publish_date values do not create real historical collection snapshots.",
            "Rows from this import must not support a multi-source or multi-week trend claim.",
        ],
    }
    _write_json(destination / "summary.json", summary)
    source_manifest = {
        "schema_version": "source_manifest_v1",
        "sources": [
            {
                "source_id": "zhaopin-historical-internal",
                "source_type": "job",
                "input": "jd_raw.sanitized.jsonl",
                "input_format": "jsonl",
                "source_name": "zhaopin",
                "publisher": "智联招聘",
                "license": "source-reference-only/team-internal",
                "metadata": {
                    "historical_import": True,
                    "single_source": True,
                    "redistribution_allowed": False,
                    "input_sha256": summary["input_sha256"],
                    "temporal_warning": (
                        "old publish_date cannot replace same-batch scrape_time collection weeks"
                    ),
                },
            }
        ],
    }
    (destination / "sources.yaml").write_text(
        yaml.safe_dump(source_manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (destination / "DATASET_CARD.md").write_text(
        f"""# INTERNAL-ONLY — 智联历史 JD 数据卡

本目录由单一智联历史文件清洗得到，不得公开分发。原始 {input_count} 条中，因邮箱/手机号过滤
{len(dropped_ids)} 条，保留 {output_count} 条、{len(retained_companies)} 家企业。输出保留未删除记录的全部
原始字段。原始数据覆盖 {len(input_companies)} 家企业，过滤后覆盖 {len(retained_companies)} 家；
`summary.json` 记录原文件 SHA-256、过滤 ID、数量及时间范围，但不记录本机绝对路径。

该数据只能作为初始历史招聘语料，不能宣称多源趋势。旧 `publish_date` 也不能替代同批
`scrape_time` 所代表的真实采集周，不能据此宣称连续多周趋势。
""",
        encoding="utf-8",
    )
    for path in (sanitized, destination / "summary.json", destination / "sources.yaml"):
        _assert_team_safe(path)
    return summary


def _copy_checked(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"symlinks are not allowed: {source}")
    _assert_team_safe(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_tree_checked(
    source: Path,
    destination: Path,
    *,
    allowed_suffixes: set[str] | None = None,
    reject_shareable_full_text: bool = False,
    reject_document_suffixes: bool = False,
) -> None:
    for candidate in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"symlinks are not allowed: {candidate}")
        if not candidate.is_file():
            continue
        if allowed_suffixes is not None and candidate.suffix.lower() not in allowed_suffixes:
            raise ValueError(f"unexpected file type in selected dataset directory: {candidate.name}")
        if reject_document_suffixes and candidate.suffix.lower() in FORBIDDEN_DOCUMENT_SUFFIXES:
            raise ValueError(f"policy/report/full-document files are not allowed: {candidate.name}")
        if reject_shareable_full_text:
            _validate_shareable_json_has_no_full_text(candidate)
        _copy_checked(candidate, destination / candidate.relative_to(source))


def _write_relocated_sources(source: Path, destination: Path, dataset_root: Path) -> None:
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    for item in value["sources"]:
        relative = _safe_relative_path(str(item["input"]), label="source input")
        relocated = PurePosixPath("private") / relative
        if not (dataset_root / Path(*relocated.parts)).is_file():
            raise FileNotFoundError(f"relocated source input does not exist: {relocated}")
        item["input"] = relocated.as_posix()
        item.setdefault("metadata", {})["team_delivery_internal_only"] = True
    destination.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _assert_team_safe(destination)


def _write_collection_report(source: Path, destination: Path) -> None:
    value = _read_json(source)
    value.setdefault("paths", {})["source_manifest"] = "sources.yaml"
    value["team_delivery"] = {
        "classification": "INTERNAL-ONLY",
        "raw_http_responses_included": False,
        "policy_or_report_fulltext_included": False,
        "source_manifest_relocated_from": "private/sources.yaml",
    }
    _write_json(destination, value)


def _dataset_card(
    stats: Mapping[str, Any],
    dataset_name: str,
    analysis_stats: Mapping[str, int] | None,
) -> str:
    counts = "\n".join(
        f"| {source} | {count} |" for source, count in stats["source_counts"].items()
    )
    pipeline_section = (
        f"""
## 首周真实流水线结果

本包保存了固定白名单内的公开分析输出：{analysis_stats['job_observations']} 个岗位观测、
{analysis_stats['trend_features']} 条趋势特征、{analysis_stats['emerging_roles']} 个新岗位候选、
{analysis_stats['job_skill_updates']} 个岗位能力更新和 {analysis_stats['kg_link_delta']} 条图谱增量。
`quality_report.json` 为 `valid`。0 个新岗位候选是首周持续性门槛的正确结果，不能据此计算或
声称趋势精度。
"""
        if analysis_stats is not None
        else ""
    )
    pipeline_directory = (
        "- `pipeline_outputs/`：首周真实运行的固定白名单输出；不含 warehouse、DuckDB 或 Qdrant。\n"
        if analysis_stats is not None
        else ""
    )
    return f"""# INTERNAL-ONLY — 真实 JD 评测数据卡

禁止公开发布、上传公开网盘、提交到 Git 或转发给团队外人员。本目录包含来自企业官网、标记为
`source-reference-only` 的完整岗位正文，只供本项目组内部评测与标注使用。

## 数据概况

- 数据集目录：`{dataset_name}`
- 采集日期：`{stats['snapshot_date']}`
- 快照周：`{stats.get('snapshot_week') or '未记录'}`
- 完整 JD：{stats['record_count']} 条
- 企业数：{stats['company_count']} 家
- 联系方式检查：未发现邮箱或电话号码
- 时间有效性：只有一个真实采集周，只可做横截面抽取/去重/RAG 评测，不能声称趋势精度

| 来源 | JD 数 |
|---|---:|
{counts}
{pipeline_section}

## 目录

- `private/jobs.full.jsonl`：{stats['record_count']} 条完整 JD 汇总。
- `private/jobs/*.jsonl`：按官网来源拆分的完整 JD；与汇总文件可精确重建。
- `sources.yaml`：已经重定位，可直接交给 `jobtrend ingest`。
- `annotations/`：A/B 独立标注、仲裁和评测模板；可能为空，也可能包含内部金标。
- `shareable/`：不含 JD 正文的 URL、哈希及采集审计索引。
{pipeline_directory}- `collection_report.json`：采集数量、来源与权利边界。

## 明确排除

本包不含 `private/raw/` HTTP 原始响应，不含政策、标准或行业报告的 PDF/HTML/DOCX/TXT
全文，不含简历、候选人姓名、邮箱或电话号码，也不含 API key。
"""


def _root_readme(
    stats: Mapping[str, Any],
    dataset_name: str,
    wheel_name: str,
    historical: Mapping[str, Any] | None,
) -> str:
    historical_section = (
        f"""
## 导入智联历史 JD

历史数据由单一智联来源的 {historical['input_record_count']} 条原始记录清洗得到；过滤 5 条含
联系方式的记录后保留 {historical['output_record_count']} 条。它只能作为历史基线语料，不能作为
多源或真实多周趋势证据。

```bash
jobtrend ingest \\
  --sources ../../datasets/historical_zhaopin/sources.yaml \\
  --warehouse runs/historical-zhaopin/warehouse
```

请不要将这个 warehouse 与合成演示或真实周快照共用；如果需要联合分析，应先由负责人明确
数据边界和运行配置。历史记录里的旧 `publish_date` 不能替代同批 `scrape_time` 采集周。
"""
        if historical is not None
        else ""
    )
    return f"""# INTERNAL-ONLY — JobTrend 组内完整交付包

本归档由“安全组件包”和“受限真实评测数据”组成。不得将整个归档公开上传或提交 Git；如果需要
对外演示，只分发 `component/`，不要分发 `datasets/`。

## 内容

- `component/`：已经通过 `LOCAL_VALIDATION.json` 的组件、源码、wheel、合成演示输出和文档。
- `datasets/{dataset_name}/`：{stats['snapshot_date']} 首周 {stats['record_count']} 条真实 JD、标注模板与审计索引。
- `MANIFEST.sha256`：除自身外，归档中每个文件的 SHA-256。
- `INTERNAL-ONLY.txt`：组内使用标记。

注意：`component/` 根目录的趋势、新岗位和能力更新文件是合成演示产物，不是真实趋势结论。
真实数据目前只有一个采集周，出现 0 个新岗位候选是预期结果。

## 安装与 5 分钟演示

需要 Python 3.11 或更高版本。下列依赖安装通常需要联网；安装完成后的合成演示不访问网络、
不需要 `DASHSCOPE_API_KEY`，也不会产生云费用。

```bash
cd component/source
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps ../dist/{wheel_name}

jobtrend --pretty run-all \\
  --sources data/samples/sources.yaml \\
  --warehouse runs/demo/warehouse \\
  --output runs/demo/analysis
```

合成演示预期至少产生 120 个岗位观测、1 个新岗位候选和 1 个岗位能力更新。始终使用独立
`--warehouse`，不要把合成演示与真实数据混入同一仓库。

## 运行真实评测数据

仍在 `component/source` 目录中执行：

```bash
jobtrend ingest \\
  --sources ../../datasets/{dataset_name}/sources.yaml \\
  --warehouse runs/real-eval-{stats['snapshot_date']}/warehouse

jobtrend analyze \\
  --warehouse runs/real-eval-{stats['snapshot_date']}/warehouse \\
  --output runs/real-eval-{stats['snapshot_date']}/analysis
```
{historical_section}

图谱始终只读导入；本组件只输出 `kg_link_delta.jsonl`，由图谱负责人审核后合并。云检索必须显式
添加 `--cloud-retrieval`；付费 Batch 还要求 `--execute --confirm SUBMIT_JOBTREND_PAID_BATCH`。

## 校验文件

解压后可在归档根目录校验逐文件哈希：

```bash
shasum -a 256 -c MANIFEST.sha256
```

数据使用限制与标注说明见 `datasets/{dataset_name}/DATASET_CARD.md` 和
`component/source/docs/annotation_guide.md`。
"""


def _write_file_manifest(root: Path) -> int:
    manifest = root / "MANIFEST.sha256"
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path != manifest),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    manifest.write_text(
        "".join(f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="ascii",
    )
    return len(files)


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if info.isdir() else 0o644
    return info


def _create_deterministic_archive(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    archive.add(source, arcname=source.name, recursive=True, filter=_tar_filter)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_team_delivery(
    component_dir: str | Path,
    snapshot_dir: str | Path,
    output_dir: str | Path,
    *,
    analysis_dir: str | Path | None = None,
    historical_jd: str | Path | None = None,
    bundle_name: str | None = None,
) -> dict[str, Any]:
    """Create one deterministic INTERNAL-ONLY archive and its checksum sidecar."""

    component = Path(component_dir).expanduser().resolve()
    snapshot = Path(snapshot_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    analysis = Path(analysis_dir).expanduser().resolve() if analysis_dir is not None else None
    historical_source = (
        Path(historical_jd).expanduser().resolve() if historical_jd is not None else None
    )
    wheel_name = _validate_component(component)
    stats = _validate_snapshot(snapshot)
    analysis_stats = _validate_analysis(analysis)
    name = _validate_bundle_name(bundle_name or f"jobtrend-team-delivery-{stats['snapshot_date']}")
    dataset_name = f"real_eval_{stats['snapshot_date']}"

    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"{name}.tar.gz"
    checksum_path = output / f"{name}.tar.gz.sha256"
    for target in (archive_path, checksum_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing team delivery: {target}")

    temporary_root = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=output))
    staging = temporary_root / name
    dataset = staging / "datasets" / dataset_name
    archive_created = False
    try:
        staging.mkdir()
        _copy_tree_checked(component, staging / "component")

        _copy_checked(
            snapshot / "private" / "jobs.full.jsonl",
            dataset / "private" / "jobs.full.jsonl",
        )
        _copy_tree_checked(snapshot / "private" / "jobs", dataset / "private" / "jobs")
        _copy_tree_checked(
            snapshot / "annotations",
            dataset / "annotations",
            allowed_suffixes=ALLOWED_ANNOTATION_SUFFIXES,
            reject_document_suffixes=True,
        )
        _copy_tree_checked(
            snapshot / "shareable",
            dataset / "shareable",
            allowed_suffixes=ALLOWED_SHAREABLE_SUFFIXES,
            reject_shareable_full_text=True,
            reject_document_suffixes=True,
        )
        dataset.mkdir(parents=True, exist_ok=True)
        _write_relocated_sources(
            snapshot / "private" / "sources.yaml", dataset / "sources.yaml", dataset
        )
        _write_collection_report(
            snapshot / "collection_report.json", dataset / "collection_report.json"
        )

        if analysis is not None:
            for filename in PIPELINE_OUTPUT_FILES:
                _copy_checked(analysis / filename, dataset / "pipeline_outputs" / filename)

        historical_summary = None
        if historical_source is not None:
            historical_summary = _package_historical_jd(
                historical_source, staging / "datasets" / "historical_zhaopin"
            )

        (dataset / "DATASET_CARD.md").write_text(
            _dataset_card(stats, dataset_name, analysis_stats), encoding="utf-8"
        )
        (staging / "README.md").write_text(
            _root_readme(stats, dataset_name, wheel_name, historical_summary), encoding="utf-8"
        )
        (staging / "INTERNAL-ONLY.txt").write_text(
            "INTERNAL-ONLY: contains source-reference-only full JD text. "
            "Do not publish, upload to public storage, or share outside the project team.\n",
            encoding="utf-8",
        )

        for candidate in sorted(staging.rglob("*"), key=lambda item: item.as_posix()):
            if candidate.is_symlink():
                raise ValueError(f"symlink unexpectedly present in staging: {candidate}")
            if candidate.is_file():
                _assert_team_safe(candidate)
        manifest_count = _write_file_manifest(staging)
        _assert_team_safe(staging / "MANIFEST.sha256")

        _create_deterministic_archive(staging, archive_path)
        archive_created = True
        archive_sha256 = _sha256_file(archive_path)
        checksum_path.write_text(f"{archive_sha256}  {archive_path.name}\n", encoding="ascii")
        return {
            "classification": "INTERNAL-ONLY",
            "archive_path": str(archive_path),
            "archive_sha256": archive_sha256,
            "checksum_path": str(checksum_path),
            "bundle_name": name,
            "dataset_name": dataset_name,
            "record_count": stats["record_count"],
            "company_count": stats["company_count"],
            "pipeline_outputs_included": analysis_stats is not None,
            "historical_record_count": (
                historical_summary["output_record_count"] if historical_summary else None
            ),
            "manifest_file_count": manifest_count,
        }
    except Exception:
        if archive_created or archive_path.exists():
            archive_path.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an INTERNAL-ONLY team archive around a validated JobTrend component"
    )
    parser.add_argument(
        "--component", required=True, type=Path, help="validated component handoff directory"
    )
    parser.add_argument(
        "--snapshot", required=True, type=Path, help="real evaluation snapshot directory"
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        help="validated first-week real analysis directory (fixed public-output allow-list)",
    )
    parser.add_argument(
        "--historical-jd",
        type=Path,
        help="optional 10,515-row single-source zhaopin jd_raw.jsonl",
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="directory for tar.gz and SHA sidecar"
    )
    parser.add_argument("--bundle-name", help="optional safe archive root name")
    args = parser.parse_args()
    result = build_team_delivery(
        args.component,
        args.snapshot,
        args.output,
        analysis_dir=args.analysis_dir,
        historical_jd=args.historical_jd,
        bundle_name=args.bundle_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
