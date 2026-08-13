"""Conservative one-shot collection of public career-site evaluation data.

This module is deliberately separate from the production ``jobtrend`` CLI.  It
collects a weekly, internal-only evaluation snapshot from a small allow-list of
official career sites.  It never logs in, applies for jobs, follows referral
links, solves challenges, or collects contact/person data.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
import yaml
from bs4 import BeautifulSoup

from .io_utils import (
    read_jsonl,
    sha256_bytes,
    sha256_file,
    sha256_text,
    stable_id,
    write_json,
    write_jsonl,
)


COLLECTOR_VERSION = "public_eval_collector_v1"
USER_AGENT = "JobTrendAcademicEvaluation/0.1 (+internal research; no personal data)"
DEFAULT_KEYWORD = "大模型"
DEFAULT_QUOTAS: dict[str, int] = {
    "tencent": 32,
    "meituan": 32,
    "xiaomi": 32,
    "baidu": 32,
    "huawei": 12,
}
SOURCE_DOMAINS = {
    "tencent": "careers.tencent.com",
    "meituan": "zhaopin.meituan.com",
    "xiaomi": "hr.xiaomi.com",
    "baidu": "talent.baidu.com",
    "huawei": "career.huawei.com",
}
COMPANIES = {
    "tencent": "腾讯",
    "meituan": "美团",
    "xiaomi": "小米",
    "baidu": "百度",
    "huawei": "华为",
}
SOURCE_NAMES = {name: f"{domain}-official" for name, domain in SOURCE_DOMAINS.items()}

_AI_TERMS = (
    "ai",
    "人工智能",
    "大模型",
    "llm",
    "agent",
    "智能体",
    "多模态",
    "机器学习",
    "深度学习",
    "生成式",
    "aigc",
    "算法",
)


class CollectionStopped(RuntimeError):
    """Raised when a source signals that automated collection must stop."""


@dataclass(frozen=True, slots=True)
class SourceResult:
    source_id: str
    records: tuple[dict[str, Any], ...]
    status: str = "completed"
    reason: str | None = None


@dataclass(slots=True)
class RateLimiter:
    delay_seconds: float = 1.1
    _last_request: dict[str, float] = field(default_factory=dict)

    def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").casefold()
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay_seconds - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[host] = time.monotonic()


class AuditedFetcher:
    """Serial, rate-limited HTTP client that saves an immutable response log."""

    def __init__(
        self,
        raw_root: str | Path,
        *,
        client: httpx.Client | None = None,
        delay_seconds: float = 1.1,
        timeout_seconds: float = 45.0,
        max_attempts: int = 3,
    ) -> None:
        self.raw_root = Path(raw_root)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
        )
        self._owns_client = client is None
        self.limiter = RateLimiter(delay_seconds)
        self.max_attempts = max(1, max_attempts)
        self.request_log: list[dict[str, Any]] = []
        self._sequences: Counter[str] = Counter()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "AuditedFetcher":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(
        self,
        source_id: str,
        purpose: str,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        safe_url = _canonical_url(url)
        response: httpx.Response | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.limiter.wait(url)
            response = self.client.request(method, url, **kwargs)
            if response.status_code in {401, 403, 429}:
                self._save_response(source_id, purpose, method, safe_url, response, attempt)
                retry_after = response.headers.get("Retry-After")
                detail = f"; Retry-After={retry_after}" if retry_after else ""
                raise CollectionStopped(
                    f"{source_id}: HTTP {response.status_code} requires collection stop{detail}"
                )
            if response.status_code < 500:
                break
            if attempt < self.max_attempts:
                time.sleep(min(8.0, float(2 ** (attempt - 1))))
        assert response is not None
        self._save_response(source_id, purpose, method, safe_url, response, attempt)
        response.raise_for_status()
        return response

    def _save_response(
        self,
        source_id: str,
        purpose: str,
        method: str,
        url: str,
        response: httpx.Response,
        attempt: int,
    ) -> None:
        body = response.content
        body_sha256 = sha256_bytes(body)
        content_type = response.headers.get("Content-Type", "")
        suffix = ".json" if "json" in content_type else ".html" if "html" in content_type else ".bin"
        self._sequences[source_id] += 1
        sequence = self._sequences[source_id]
        safe_purpose = re.sub(r"[^a-z0-9_-]+", "-", purpose.casefold()).strip("-") or "response"
        relative = Path(source_id) / f"{sequence:04d}_{safe_purpose}_{body_sha256[:12]}{suffix}"
        target = self.raw_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(body)
        self.request_log.append(
            {
                "source_id": source_id,
                "purpose": purpose,
                "method": method.upper(),
                "url": url,
                "final_url": _canonical_url(str(response.url)),
                "status_code": response.status_code,
                "content_type": content_type,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "body_sha256": body_sha256,
                "body_bytes": len(body),
                "raw_path": relative.as_posix(),
                "attempt": attempt,
            }
        )


def collect_public_evaluation_snapshot(
    output_root: str | Path,
    *,
    snapshot_date: date | None = None,
    quotas: Mapping[str, int] | None = None,
    keyword: str = DEFAULT_KEYWORD,
    delay_seconds: float = 1.1,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Collect and materialize one auditable official-career-site snapshot.

    Full text is marked ``source-reference-only`` and is intentionally written
    under ``private/``.  It must not be included in a public hand-off archive.
    """

    chosen_date = snapshot_date or datetime.now().astimezone().date()
    root = Path(output_root).expanduser().resolve() / chosen_date.isoformat()
    if (root / "collection_report.json").exists():
        raise FileExistsError(f"snapshot already finalized: {root}")
    private_root = root / "private"
    raw_root = private_root / "raw"
    job_root = private_root / "jobs"
    public_root = root / "shareable"
    annotation_root = root / "annotations"
    for directory in (raw_root, job_root, public_root, annotation_root):
        directory.mkdir(parents=True, exist_ok=True)

    collected_at = datetime.now().astimezone().replace(microsecond=0)
    snapshot_week = collected_at.strftime("%G-W%V")
    requested_quotas = {**DEFAULT_QUOTAS, **dict(quotas or {})}
    unknown = sorted(set(requested_quotas) - set(DEFAULT_QUOTAS))
    if unknown:
        raise ValueError(f"unsupported sources: {', '.join(unknown)}")
    if any(int(value) <= 0 for value in requested_quotas.values()):
        raise ValueError("all source quotas must be positive")

    adapters: dict[str, Callable[..., SourceResult]] = {
        "tencent": _collect_tencent,
        "meituan": _collect_meituan,
        "xiaomi": _collect_xiaomi,
        "baidu": _collect_baidu,
        "huawei": _collect_huawei,
    }
    results: list[SourceResult] = []
    robots_rows: list[dict[str, Any]] = []
    with AuditedFetcher(raw_root, client=client, delay_seconds=delay_seconds) as fetcher:
        for source_id in DEFAULT_QUOTAS:
            if source_id not in requested_quotas:
                continue
            target_paths = _target_paths(source_id)
            robots = inspect_robots(fetcher, source_id, target_paths)
            robots_rows.append(robots)
            if robots["decision"] == "disallow":
                results.append(
                    SourceResult(source_id, (), status="skipped", reason="robots_disallow")
                )
                continue
            try:
                result = adapters[source_id](
                    fetcher,
                    quota=int(requested_quotas[source_id]),
                    keyword=keyword,
                    collected_at=collected_at,
                    snapshot_week=snapshot_week,
                )
            except CollectionStopped as exc:
                result = SourceResult(source_id, (), status="stopped", reason=str(exc))
            results.append(result)

        request_log = list(fetcher.request_log)

    all_records: list[dict[str, Any]] = []
    for result in results:
        records = sorted(result.records, key=lambda item: (item["external_id"], item["job_title"]))
        write_jsonl(job_root / f"{result.source_id}.jsonl", records)
        all_records.extend(records)
    all_records = _deduplicate_external_records(all_records)
    write_jsonl(private_root / "jobs.full.jsonl", all_records)
    write_jsonl(public_root / "jobs.reference.jsonl", (_reference_record(row) for row in all_records))
    write_jsonl(public_root / "http_requests.jsonl", request_log)
    write_jsonl(public_root / "robots_checks.jsonl", robots_rows)

    source_manifest = _build_source_manifest(results, root, collected_at, snapshot_week)
    manifest_path = private_root / "sources.yaml"
    manifest_path.write_text(
        yaml.safe_dump(source_manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    snapshot_rows = _snapshot_rows(
        results,
        request_log,
        robots_rows,
        collected_at,
        snapshot_week,
        raw_root,
    )
    write_jsonl(public_root / "collection_snapshots.jsonl", snapshot_rows)
    annotation = build_annotation_templates(all_records, annotation_root)

    status_counts = Counter(result.status for result in results)
    source_counts = Counter(row["source_id"] for row in all_records)
    report: dict[str, Any] = {
        "schema_version": "public_eval_collection_report_v1",
        "collector_version": COLLECTOR_VERSION,
        "snapshot_date": chosen_date.isoformat(),
        "snapshot_week": snapshot_week,
        "collected_at": collected_at.isoformat(),
        "keyword": keyword,
        "rights": {
            "license": "source-reference-only",
            "redistribution_allowed": False,
            "note": "Full JD text is internal evaluation material; share only the reference index.",
        },
        "requested_quotas": requested_quotas,
        "source_counts": dict(sorted(source_counts.items())),
        "company_count": len({row["company_name"] for row in all_records}),
        "record_count": len(all_records),
        "records_with_responsibilities": sum(bool(row["responsibilities"].strip()) for row in all_records),
        "records_with_requirements": sum(bool(row["requirements"].strip()) for row in all_records),
        "records_with_published_at": sum(bool(row.get("publish_date")) for row in all_records),
        "unique_external_ids": len({(row["source_id"], row["external_id"]) for row in all_records}),
        "unique_content_sha256": len({row["content_sha256"] for row in all_records}),
        "source_status_counts": dict(status_counts),
        "source_results": [
            {
                "source_id": result.source_id,
                "status": result.status,
                "reason": result.reason,
                "record_count": len(result.records),
            }
            for result in results
        ],
        "http_request_count": len(request_log),
        "annotation": annotation,
        "trend_validity": {
            "valid_for_cross_sectional_extraction_eval": len(all_records) >= 100,
            "valid_for_temporal_trend_eval": False,
            "reason": "Only one real collection week exists; published dates do not substitute for snapshots.",
        },
        "paths": {
            "private_jobs": "private/jobs.full.jsonl",
            "source_manifest": "private/sources.yaml",
            "shareable_reference": "shareable/jobs.reference.jsonl",
            "snapshot_manifest": "shareable/collection_snapshots.jsonl",
            "annotation_dir": "annotations",
        },
    }
    write_json(root / "collection_report.json", report)
    return report


def inspect_robots(
    fetcher: AuditedFetcher, source_id: str, target_paths: Sequence[str]
) -> dict[str, Any]:
    domain = SOURCE_DOMAINS[source_id]
    url = f"https://{domain}/robots.txt"
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        response = fetcher.request(source_id, "robots", "GET", url)
    except CollectionStopped as exc:
        return {
            "source_id": source_id,
            "robots_url": url,
            "checked_at": checked_at,
            "status_code": None,
            "classification": "blocked",
            "decision": "disallow",
            "target_paths": list(target_paths),
            "reason": str(exc),
        }
    except httpx.HTTPError as exc:
        return {
            "source_id": source_id,
            "robots_url": url,
            "checked_at": checked_at,
            "status_code": getattr(getattr(exc, "response", None), "status_code", None),
            "classification": "missing_or_unavailable",
            "decision": "no_machine_readable_rule",
            "target_paths": list(target_paths),
        }

    text = response.text.lstrip("\ufeff").strip()
    content_type = response.headers.get("Content-Type", "").casefold()
    machine_readable = bool(re.search(r"(?im)^\s*user-agent\s*:", text)) and "html" not in content_type
    if not machine_readable:
        return {
            "source_id": source_id,
            "robots_url": url,
            "checked_at": checked_at,
            "status_code": response.status_code,
            "classification": "soft_missing" if response.status_code == 200 else "missing",
            "decision": "no_machine_readable_rule",
            "target_paths": list(target_paths),
        }
    parser = RobotFileParser()
    parser.set_url(url)
    parser.parse(text.splitlines())
    allowed = [parser.can_fetch(USER_AGENT, f"https://{domain}{path}") for path in target_paths]
    return {
        "source_id": source_id,
        "robots_url": url,
        "checked_at": checked_at,
        "status_code": response.status_code,
        "classification": "machine_readable",
        "decision": "allow" if all(allowed) else "disallow",
        "target_paths": list(target_paths),
        "allowed": allowed,
        "robots_sha256": sha256_text(text),
    }


def build_annotation_templates(
    records: Sequence[Mapping[str, Any]], output_dir: str | Path, *, calibration_size: int = 20
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # Keep exact and high-similarity versions in one split.  A row-level random
    # split would leak nearly identical vacancies into calibration and test.
    groups = _near_version_groups(records)
    ordered_groups = sorted(
        groups,
        key=lambda group: sha256_text(
            "eval-split-v2:" + ":".join(sorted(str(row["document_id"]) for row in group))
        ),
    )
    calibration_ids: set[str] = set()
    for group in ordered_groups:
        if len(calibration_ids) >= calibration_size:
            break
        calibration_ids.update(str(row["document_id"]) for row in group)

    def rows_for(annotator: str) -> Iterable[dict[str, Any]]:
        for row in sorted(records, key=lambda item: str(item["document_id"])):
            yield {
                "document_id": row["document_id"],
                "document_sha256": row["content_sha256"],
                "split": "calibration" if row["document_id"] in calibration_ids else "test",
                "annotator": annotator,
                "annotation_version": "v1",
                "annotation_status": "unlabelled",
                "normalized_title": "",
                "company": row["company_name"],
                "region": row.get("location") or "",
                "mentions": [],
                "notes": "",
            }

    write_jsonl(output / "jd_annotations_A.jsonl", rows_for("A"))
    write_jsonl(output / "jd_annotations_B.jsonl", rows_for("B"))
    write_jsonl(output / "jd_annotations_adjudicated.jsonl", [])
    pairs, pair_sampling = _dedup_candidate_pairs(records, limit=400)
    pair_header = "left_document_id,right_document_id,annotator,label,same_vacancy,reason\n"
    for annotator in ("A", "B"):
        body = "".join(
            f'{left},{right},{annotator},,,\n' for left, right in pairs
        )
        (output / f"dedup_pairs_{annotator}.csv").write_text(pair_header + body, encoding="utf-8")
    (output / "dedup_pairs.csv").write_text(pair_header, encoding="utf-8")
    write_json(output / "dedup_pair_sampling_manifest.json", pair_sampling)

    query_types = ("policy_claim", "responsibility", "skill")
    for annotator in ("A", "B"):
        write_jsonl(
            output / f"rag_queries_{annotator}.jsonl",
            (
                {
                    "query_id": f"rag-{index:03d}",
                    "cutoff_at": "",
                    "query_text": "",
                    "target_type": query_types[(index - 1) // 20],
                    "relevant_evidence_ids": [],
                    "corpus_sha256": "",
                    "annotator": annotator,
                    "annotation_status": "unlabelled",
                }
                for index in range(1, 61)
            ),
        )
    write_jsonl(output / "rag_queries.jsonl", [])
    (output / "emerging_role_labels.csv").write_text(
        "as_of,rank,role_id,canonical_title,annotator,label,closest_kg_job_ids,evidence_ids,reason\n",
        encoding="utf-8",
    )
    (output / "skill_change_labels.csv").write_text(
        "as_of,canonical_role,kg_job_id,skill_name,kg_skill_id,change_type,baseline_share,recent_share,"
        "supporting_companies,supporting_sources,annotator,label,evidence_ids\n",
        encoding="utf-8",
    )
    split_manifest = {
        "schema_version": "jobtrend_eval_split_v1",
        "method": (
            "Group exact/high-similarity same-company versions first; order groups by "
            "sha256(eval-split-v2:group_document_ids); never row-random split."
        ),
        "calibration_count": len(calibration_ids),
        "test_count": max(0, len(records) - len(calibration_ids)),
        "calibration_document_ids": sorted(calibration_ids),
        "test_document_ids": sorted(
            row["document_id"] for row in records if row["document_id"] not in calibration_ids
        ),
        "gold_status": "unlabelled",
        "leakage_warning": "Do not tune prompts, aliases, or thresholds on the test IDs.",
    }
    write_json(output / "split_manifest.json", split_manifest)
    return {
        "calibration_count": split_manifest["calibration_count"],
        "test_count": split_manifest["test_count"],
        "gold_status": "unlabelled",
        "dedup_pair_count": len(pairs),
        "rag_query_template_count_per_annotator": 60,
    }


def validate_evaluation_snapshot(
    snapshot_dir: str | Path,
    *,
    warehouse_dir: str | Path | None = None,
    analysis_dir: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate provenance, privacy, split integrity, and pipeline round-trip.

    This is a structural readiness check, not a substitute for human gold
    labels.  Acceptance metrics deliberately remain ``null`` until the two
    annotation files have been independently completed and adjudicated.
    """

    root = Path(snapshot_dir).expanduser().resolve()
    collection_report = json.loads((root / "collection_report.json").read_text(encoding="utf-8"))
    jobs = list(read_jsonl(root / "private" / "jobs.full.jsonl"))
    references = list(read_jsonl(root / "shareable" / "jobs.reference.jsonl"))
    snapshots = list(read_jsonl(root / "shareable" / "collection_snapshots.jsonl"))
    annotations_a = list(read_jsonl(root / "annotations" / "jd_annotations_A.jsonl"))
    annotations_b = list(read_jsonl(root / "annotations" / "jd_annotations_B.jsonl"))
    split = json.loads((root / "annotations" / "split_manifest.json").read_text(encoding="utf-8"))
    pair_manifest = json.loads(
        (root / "annotations" / "dedup_pair_sampling_manifest.json").read_text(encoding="utf-8")
    )

    email_pattern = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
    phone_pattern = re.compile(
        r"(?<!\d)(?:1[3-9]\d{9}|(?:\+?86[- ]?)?0\d{2,3}[- ]?\d{7,8})(?!\d)"
    )
    required_fields = {
        "document_id",
        "external_id",
        "source_id",
        "job_title",
        "company_name",
        "responsibilities",
        "requirements",
        "jd_text",
        "url",
        "collected_at",
        "content_sha256",
        "snapshot_id",
        "snapshot_week",
    }
    allowed_job_hosts = {
        *SOURCE_DOMAINS.values(),
        "xiaomi.jobs.f.mioffice.cn",
    }
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(condition), "detail": detail})

    check("minimum_records", len(jobs) >= 100, len(jobs))
    check("minimum_companies", len({row.get("company_name") for row in jobs}) >= 5, collection_report.get("source_counts"))
    missing = {
        str(row.get("document_id") or f"row-{index}"): sorted(required_fields - set(row))
        for index, row in enumerate(jobs, start=1)
        if required_fields - set(row)
    }
    check("required_fields", not missing, missing)
    bad_hashes = [
        row["document_id"]
        for row in jobs
        if sha256_text(str(row.get("jd_text") or "")) != row.get("content_sha256")
    ]
    check("content_sha256", not bad_hashes, bad_hashes)
    ids = [(str(row.get("source_id")), str(row.get("external_id"))) for row in jobs]
    check("unique_source_external_ids", len(ids) == len(set(ids)), len(set(ids)))
    invalid_urls = [
        row["document_id"]
        for row in jobs
        if urlsplit(str(row.get("url") or "")).scheme != "https"
        or (urlsplit(str(row.get("url") or "")).hostname or "").casefold() not in allowed_job_hosts
    ]
    check("official_https_urls", not invalid_urls, invalid_urls)
    personal_data_hits = [
        row["document_id"]
        for row in jobs
        if email_pattern.search(str(row.get("jd_text") or ""))
        or phone_pattern.search(str(row.get("jd_text") or ""))
    ]
    check("no_contact_personal_data", not personal_data_hits, personal_data_hits)
    full_text_reference_fields = {
        row["document_id"]
        for row in references
        if any(field in row for field in ("jd_text", "responsibilities", "requirements"))
    }
    check("shareable_index_has_no_full_text", not full_text_reference_fields, sorted(full_text_reference_fields))
    check("snapshot_rows_cover_sources", len(snapshots) == len({row["source_id"] for row in jobs}), len(snapshots))
    check("first_week_not_temporal_trend", all(not row.get("valid_for_trend") for row in snapshots), None)

    all_ids = {str(row["document_id"]) for row in jobs}
    calibration_ids = set(map(str, split.get("calibration_document_ids") or []))
    test_ids = set(map(str, split.get("test_document_ids") or []))
    check("split_disjoint", not calibration_ids & test_ids, sorted(calibration_ids & test_ids))
    check("split_complete", calibration_ids | test_ids == all_ids, len(calibration_ids | test_ids))
    by_hash: dict[str, set[str]] = {}
    for row in jobs:
        split_name = "calibration" if row["document_id"] in calibration_ids else "test"
        by_hash.setdefault(str(row["content_sha256"]), set()).add(split_name)
    leaked_hashes = sorted(value for value, split_names in by_hash.items() if len(split_names) > 1)
    check("no_exact_version_split_leakage", not leaked_hashes, leaked_hashes)
    annotation_a_ids = {str(row["document_id"]) for row in annotations_a}
    annotation_b_ids = {str(row["document_id"]) for row in annotations_b}
    check("dual_annotation_coverage", annotation_a_ids == annotation_b_ids == all_ids, len(annotation_a_ids))

    pair_sets: list[set[tuple[str, str]]] = []
    for annotator in ("A", "B"):
        with (root / "annotations" / f"dedup_pairs_{annotator}.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            pair_sets.append(
                {
                    tuple(sorted((row["left_document_id"], row["right_document_id"])))
                    for row in csv.DictReader(handle)
                }
            )
    check(
        "dedup_pair_sampling",
        pair_sets[0] == pair_sets[1] and len(pair_sets[0]) == int(pair_manifest.get("pair_count") or 0),
        len(pair_sets[0]),
    )

    warehouse_summary: dict[str, Any] | None = None
    if warehouse_dir is not None:
        from .warehouse import Warehouse

        warehouse = Warehouse(warehouse_dir)
        documents = warehouse.load("documents")
        evidence = warehouse.load("evidence")
        document_ids = {item.document_id for item in documents}
        dangling_evidence = [item.evidence_id for item in evidence if item.document_id not in document_ids]
        warehouse_summary = {
            "document_count": len(documents),
            "evidence_count": len(evidence),
            "dangling_evidence_count": len(dangling_evidence),
        }
        check("warehouse_roundtrip_count", len(documents) == len(jobs), warehouse_summary)
        check("warehouse_evidence_references", not dangling_evidence, dangling_evidence)

    analysis_summary: dict[str, Any] | None = None
    if analysis_dir is not None:
        analysis_path = Path(analysis_dir)
        manifest = json.loads((analysis_path / "manifest.json").read_text(encoding="utf-8"))
        quality_path = analysis_path / "quality_report.json"
        quality = (
            json.loads(quality_path.read_text(encoding="utf-8")).get("status")
            if quality_path.exists()
            else None
        )
        analysis_summary = {
            "quality": quality,
            "counts": manifest.get("counts"),
            "manifest_sha256": sha256_file(analysis_path / "manifest.json"),
            "quality_report_sha256": sha256_file(quality_path) if quality_path.exists() else None,
        }
        check("offline_analysis_valid", quality == "valid", analysis_summary)

    passed = all(item["passed"] for item in checks)
    report: dict[str, Any] = {
        "schema_version": "real_eval_readiness_v1",
        "snapshot_date": collection_report.get("snapshot_date"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "structural_pass" if passed else "failed",
        "checks": checks,
        "counts": {
            "jobs": len(jobs),
            "companies": len({row.get("company_name") for row in jobs}),
            "sources": len({row.get("source_id") for row in jobs}),
            "annotation_A": len(annotations_a),
            "annotation_B": len(annotations_b),
            "dedup_pairs": len(pair_sets[0]),
        },
        "warehouse": warehouse_summary,
        "analysis": analysis_summary,
        "gold_evaluation": {
            "status": "pending_double_annotation_and_adjudication",
            "jd_field_precision": None,
            "jd_field_recall": None,
            "jd_field_f1": None,
            "skill_precision": None,
            "skill_recall": None,
            "skill_f1": None,
            "near_duplicate_precision": None,
            "rag_recall_at_20": None,
            "emerging_role_precision_at_10": None,
            "skill_change_f1": None,
        },
        "temporal_evaluation": {
            "status": "not_yet_eligible",
            "real_snapshot_weeks": 1,
            "minimum_weeks_for_persistence_gate": 2,
            "minimum_weeks_for_full_112_day_window": 16,
        },
    }
    destination = Path(output_path) if output_path else root / "shareable" / "evaluation_readiness.json"
    write_json(destination, report)
    return report


def summarize_authoritative_corpus(
    warehouse_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write a reference-only readiness summary for the external evidence corpus.

    The authoritative warehouse may contain copyrighted source text needed for
    local retrieval evaluation.  This export intentionally includes only
    provenance, hashes, parse statistics, and rights metadata; it never writes
    document or evidence text.
    """

    from .warehouse import Warehouse

    warehouse = Warehouse(warehouse_dir)
    documents = warehouse.load_documents()
    evidence = warehouse.load_evidence()
    evidence_counts = Counter(item.document_id for item in evidence)
    rows: list[dict[str, Any]] = []
    for document in sorted(
        documents,
        key=lambda item: (str(item.metadata.get("source_id") or ""), item.document_id),
    ):
        source_id = str(document.metadata.get("source_id") or document.document_id)
        text_char_count = len(document.text)
        evidence_count = int(evidence_counts.get(document.document_id, 0))
        evidence_ready = (
            document.parse_status == "parsed" and text_char_count >= 100 and evidence_count > 0
        )
        rows.append(
            {
                "schema_version": "authoritative_eval_reference_v1",
                "source_id": source_id,
                "document_id": document.document_id,
                "source_type": document.source_type,
                "source_name": document.source_name,
                "publisher": document.publisher,
                "title": document.title,
                "uri": document.uri,
                "published_at": (
                    document.published_at.isoformat() if document.published_at else None
                ),
                "collected_at": document.collected_at.isoformat(),
                "raw_sha256": document.raw_sha256,
                "parse_status": document.parse_status,
                "parser_version": document.parser_version,
                "parser_backend": document.metadata.get("parser_backend"),
                "detected_format": document.metadata.get("detected_format"),
                "text_char_count": text_char_count,
                "evidence_count": evidence_count,
                "evidence_ready": evidence_ready,
                "license": document.license,
                "rights": document.metadata.get("rights") or {},
            }
        )

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference_path = output / "authoritative_documents.reference.jsonl"
    report_path = output / "authoritative_collection_report.json"
    write_jsonl(reference_path, rows)
    metadata_only = [row["source_id"] for row in rows if not row["evidence_ready"]]
    source_type_counts = dict(sorted(Counter(row["source_type"] for row in rows).items()))
    report: dict[str, Any] = {
        "schema_version": "authoritative_eval_collection_report_v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": (
            "empty"
            if not rows
            else "evidence_ready"
            if not metadata_only
            else "partial_evidence_ready"
        ),
        "document_count": len(rows),
        "source_type_counts": source_type_counts,
        "policy_or_standard_count": sum(
            row["source_type"] in {"policy", "occupational_standard"} for row in rows
        ),
        "industry_report_count": sum(
            row["source_type"] == "industry_report" for row in rows
        ),
        "evidence_count": len(evidence),
        "evidence_ready_count": len(rows) - len(metadata_only),
        "metadata_only_count": len(metadata_only),
        "metadata_only_source_ids": metadata_only,
        "rights": {
            "redistribution_allowed": False,
            "fulltext_in_handoff": False,
            "reference_export_contains_text": False,
        },
        "paths": {
            "reference_index": reference_path.name,
        },
        "limitations": (
            "Metadata-only sources remain valid provenance records but are excluded from automatic "
            "RAG scoring until a reviewable text capture is available."
        ),
    }
    write_json(report_path, report)
    return report


def _near_version_groups(records: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    fingerprints = [_record_fingerprint(row) for row in records]
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if records[left].get("company_name") != records[right].get("company_name"):
                continue
            if records[left].get("content_sha256") == records[right].get("content_sha256"):
                union(left, right)
                continue
            if _fingerprint_similarity(fingerprints[left], fingerprints[right]) >= 0.82:
                union(left, right)
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for index, row in enumerate(records):
        grouped.setdefault(find(index), []).append(row)
    return list(grouped.values())


def _dedup_candidate_pairs(
    records: Sequence[Mapping[str, Any]], *, limit: int
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    fingerprints = [_record_fingerprint(row) for row in records]
    exact: list[tuple[float, str, str]] = []
    near: list[tuple[float, str, str]] = []
    negatives: list[tuple[float, str, str]] = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            left_row, right_row = records[left], records[right]
            left_id, right_id = sorted(
                (str(left_row["document_id"]), str(right_row["document_id"]))
            )
            similarity = _fingerprint_similarity(fingerprints[left], fingerprints[right])
            if left_row.get("content_sha256") == right_row.get("content_sha256"):
                exact.append((1.0, left_id, right_id))
            elif left_row.get("company_name") == right_row.get("company_name"):
                near.append((similarity, left_id, right_id))
            else:
                negatives.append((similarity, left_id, right_id))
    exact.sort(key=lambda row: (-row[0], row[1], row[2]))
    near.sort(key=lambda row: (-row[0], row[1], row[2]))
    # Mix deceptively similar negatives with deterministic ordinary negatives.
    negatives.sort(key=lambda row: (-row[0], sha256_text(f"pair:{row[1]}:{row[2]}")))
    selected: list[tuple[float, str, str, str]] = []
    selected.extend((*row, "exact_hash") for row in exact[:40])
    selected.extend((*row, "near_candidate") for row in near[:80])
    remaining = max(0, limit - len(selected))
    selected.extend((*row, "hard_or_random_negative") for row in negatives[:remaining])
    selected = selected[:limit]
    pairs = [(left, right) for _, left, right, _ in selected]
    strata = Counter(stratum for *_, stratum in selected)
    return pairs, {
        "schema_version": "dedup_pair_sampling_v1",
        "pair_count": len(pairs),
        "strata_counts": dict(strata),
        "labels_present": False,
        "annotator_warning": "Sampling strata are not labels; A and B must decide independently.",
        "pair_set_sha256": sha256_text("\n".join(f"{left},{right}" for left, right in pairs)),
    }


def _record_fingerprint(record: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    title = re.sub(r"[（(][^）)]*[）)]|\bJ\d+\b|[\s\-_/]+", "", str(record.get("job_title") or ""), flags=re.I)
    body = str(record.get("jd_text") or "")
    return _character_ngrams(title.casefold(), 2), _character_ngrams(body.casefold(), 4)


def _character_ngrams(value: str, size: int) -> set[str]:
    compact = re.sub(r"\s+", "", value)
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _fingerprint_similarity(
    left: tuple[set[str], set[str]], right: tuple[set[str], set[str]]
) -> float:
    title = _jaccard(left[0], right[0])
    body = _jaccard(left[1], right[1])
    return 0.25 * title + 0.75 * body


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _collect_tencent(
    fetcher: AuditedFetcher,
    *,
    quota: int,
    keyword: str,
    collected_at: datetime,
    snapshot_week: str,
) -> SourceResult:
    source_id = "tencent"
    list_url = "https://careers.tencent.com/tencentcareer/api/post/Query"
    candidates: list[dict[str, Any]] = []
    page = 1
    while len(candidates) < quota and page <= 20:
        response = fetcher.request(
            source_id,
            f"list-{page}",
            "GET",
            list_url,
            params={
                "countryId": "",
                "cityId": "",
                "bgIds": "",
                "productId": "",
                "categoryId": "",
                "parentCategoryId": "",
                "attrId": "",
                "keyword": keyword,
                "pageIndex": page,
                "pageSize": 20,
                "language": "zh-cn",
                "area": "cn",
            },
            headers={"Referer": "https://careers.tencent.com/search.html"},
        )
        payload = _json_payload(response, source_id)
        if payload.get("Code") != 200:
            raise ValueError(f"{source_id}: list API returned non-success Code")
        data = payload.get("Data") or {}
        posts = data.get("Posts") or []
        for post in posts:
            if str(post.get("CountryName") or "") not in {"", "中国"}:
                continue
            if _is_ai_record(post.get("RecruitPostName"), post.get("Responsibility")):
                candidates.append(dict(post))
        if not posts or page * 20 >= int(data.get("Count") or 0):
            break
        page += 1

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    detail_url = "https://careers.tencent.com/tencentcareer/api/post/ByPostId"
    for candidate in candidates:
        external_id = str(candidate.get("PostId") or "").strip()
        if not external_id or external_id in seen:
            continue
        response = fetcher.request(
            source_id,
            f"detail-{external_id}",
            "GET",
            detail_url,
            params={"postId": external_id, "language": "zh-cn"},
            headers={"Referer": f"https://careers.tencent.com/jobdesc.html?postId={external_id}"},
        )
        payload = _json_payload(response, source_id)
        detail = payload.get("Data") or {}
        record = _record(
            source_id=source_id,
            external_id=external_id,
            title=detail.get("RecruitPostName") or candidate.get("RecruitPostName"),
            company=COMPANIES[source_id],
            region=detail.get("LocationName") or candidate.get("LocationName"),
            industry="互联网/人工智能",
            responsibilities=detail.get("Responsibility") or candidate.get("Responsibility"),
            requirements=detail.get("Requirement"),
            url=f"https://careers.tencent.com/jobdesc.html?postId={external_id}",
            published_at=None,
            updated_at=_parse_chinese_date(detail.get("LastUpdateTime") or candidate.get("LastUpdateTime")),
            collected_at=collected_at,
            snapshot_week=snapshot_week,
            extra={
                "business_group": detail.get("BGName") or candidate.get("BGName"),
                "product": detail.get("ProductName") or candidate.get("ProductName"),
                "category": detail.get("CategoryName") or candidate.get("CategoryName"),
                "experience": detail.get("RequireWorkYearsName") or candidate.get("RequireWorkYearsName"),
                "introduction": detail.get("Introduction"),
                "department_introduction": detail.get("DepartmentIntroduction"),
            },
        )
        if _valid_full_record(record):
            records.append(record)
            seen.add(external_id)
        if len(records) >= quota:
            break
    return SourceResult(source_id, tuple(records))


def _collect_meituan(
    fetcher: AuditedFetcher,
    *,
    quota: int,
    keyword: str,
    collected_at: datetime,
    snapshot_week: str,
) -> SourceResult:
    source_id = "meituan"
    url = "https://zhaopin.meituan.com/api/official/job/getJobList"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(records) < quota and page <= 20:
        response = fetcher.request(
            source_id,
            f"list-{page}",
            "POST",
            url,
            json={
                "page": {"pageNo": page, "pageSize": 20},
                "jobShareType": "1",
                "keywords": keyword,
                "cityList": [],
                "department": [],
                "jfJgList": [],
                "jobType": [],
                "typeCode": [],
                "specialCode": [],
            },
            headers={"Referer": "https://zhaopin.meituan.com/web/social"},
        )
        payload = _json_payload(response, source_id)
        data = payload.get("data") or {}
        posts = data.get("list") or []
        for post in posts:
            external_id = str(post.get("jobUnionId") or "").strip()
            if not external_id or external_id in seen:
                continue
            if not _is_ai_record(post.get("name"), post.get("jobDuty"), post.get("jobRequirement")):
                continue
            cities = [str(item.get("name") or "") for item in post.get("cityList") or [] if item.get("name")]
            departments = [
                str(item.get("name") or item.get("label") or "")
                for item in post.get("department") or []
                if isinstance(item, Mapping)
            ]
            record = _record(
                source_id=source_id,
                external_id=external_id,
                title=post.get("name"),
                company=COMPANIES[source_id],
                region="/".join(cities),
                industry="本地生活/人工智能",
                responsibilities=post.get("jobDuty"),
                requirements=post.get("jobRequirement"),
                url=(
                    "https://zhaopin.meituan.com/web/position/detail?"
                    + urlencode({"highlightType": "social", "jobUnionId": external_id})
                ),
                published_at=_milliseconds_date(post.get("firstPostTime")),
                updated_at=_milliseconds_date(post.get("refreshTime")),
                collected_at=collected_at,
                snapshot_week=snapshot_week,
                extra={
                    "job_type": post.get("jobType"),
                    "job_family": post.get("jobFamily"),
                    "job_family_group": post.get("jobFamilyGroup"),
                    "departments": departments,
                    "work_year": post.get("workYear"),
                },
            )
            if _valid_full_record(record):
                records.append(record)
                seen.add(external_id)
            if len(records) >= quota:
                break
        total = int((data.get("page") or {}).get("totalCount") or 0)
        if not posts or page * 20 >= total:
            break
        page += 1
    return SourceResult(source_id, tuple(records))


def _collect_xiaomi(
    fetcher: AuditedFetcher,
    *,
    quota: int,
    keyword: str,
    collected_at: datetime,
    snapshot_week: str,
) -> SourceResult:
    source_id = "xiaomi"
    url = "https://hr.xiaomi.com/website/api/agent/searchJobPage"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(records) < quota and page <= 20:
        response = fetcher.request(
            source_id,
            f"list-{page}",
            "GET",
            url,
            params={"keyword": keyword, "cityZhNames": "", "pageSize": 20, "pageNum": page},
            headers={"Referer": "https://hr.xiaomi.com/website/opportunities.html"},
        )
        payload = _json_payload(response, source_id)
        if payload.get("code") != 0:
            raise ValueError(f"{source_id}: list API returned non-success code")
        data = payload.get("data") or {}
        posts = data.get("list") or []
        for post in posts:
            external_id = str(post.get("jobPostId") or post.get("jobId") or post.get("id") or "").strip()
            if not external_id or external_id in seen:
                continue
            if not _is_ai_record(post.get("title"), post.get("description"), post.get("requirement")):
                continue
            record = _record(
                source_id=source_id,
                external_id=external_id,
                title=post.get("title"),
                company=COMPANIES[source_id],
                region="/".join(str(value) for value in post.get("cityZhNames") or []),
                industry="智能硬件/人工智能",
                responsibilities=post.get("description"),
                requirements=post.get("requirement"),
                url=post.get("url"),
                published_at=_iso_date(post.get("publishTime")),
                updated_at=None,
                collected_at=collected_at,
                snapshot_week=snapshot_week,
                extra={
                    "department": post.get("levelOneDeptName"),
                    "employment_type": {1: "social", 2: "campus", 3: "intern", 4: "top_talent"}.get(
                        post.get("type"), str(post.get("type") or "")
                    ),
                    "job_code": post.get("larkJobCode"),
                },
            )
            if _valid_full_record(record):
                records.append(record)
                seen.add(external_id)
            if len(records) >= quota:
                break
        total = int(data.get("total") or 0)
        if not posts or page * 20 >= total:
            break
        page += 1
    return SourceResult(source_id, tuple(records))


def _collect_baidu(
    fetcher: AuditedFetcher,
    *,
    quota: int,
    keyword: str,
    collected_at: datetime,
    snapshot_week: str,
) -> SourceResult:
    source_id = "baidu"
    url = "https://talent.baidu.com/httservice/getPostListNew"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Social first, then campus/internship, so the evaluation set is not only campus data.
    recruitment_types = (("SOCIAL", ""), ("GRADUATE", "1"), ("INTERN", ""))
    target_per_type = max(1, quota // len(recruitment_types))
    for recruit_type, project_type in recruitment_types:
        page = 1
        type_count = 0
        while len(records) < quota and page <= 30:
            response = fetcher.request(
                source_id,
                f"list-{recruit_type.casefold()}-{page}",
                "POST",
                url,
                data={
                    "recruitType": recruit_type,
                    "pageSize": "10",
                    "keyWord": keyword,
                    "curPage": str(page),
                    "projectType": project_type,
                },
                headers={"Referer": "https://talent.baidu.com/jobs/list"},
            )
            payload = _json_payload(response, source_id)
            if payload.get("status") != "ok":
                raise ValueError(f"{source_id}: list API returned non-success status")
            data = payload.get("data") or {}
            posts = data.get("list") or []
            for post in posts:
                external_id = str(post.get("postId") or post.get("jobId") or "").strip()
                if not external_id or external_id in seen:
                    continue
                if not _is_ai_record(post.get("name"), post.get("workContent"), post.get("serviceCondition")):
                    continue
                record = _record(
                    source_id=source_id,
                    external_id=external_id,
                    title=post.get("name"),
                    company=COMPANIES[source_id],
                    region=post.get("workPlace"),
                    industry="互联网/人工智能",
                    responsibilities=post.get("workContent"),
                    requirements=post.get("serviceCondition"),
                    url=f"https://talent.baidu.com/jobs/detail/{recruit_type}/{external_id}",
                    published_at=_iso_date(post.get("publishDate")),
                    updated_at=_iso_date(post.get("updateDate")),
                    collected_at=collected_at,
                    snapshot_week=snapshot_week,
                    extra={
                        "employment_type": recruit_type.casefold(),
                        "job_type": post.get("postType"),
                        "business_group": post.get("bgShortName"),
                        "work_years": post.get("workYears"),
                        "recruit_num": post.get("recruitNum"),
                    },
                )
                if _valid_full_record(record):
                    records.append(record)
                    seen.add(external_id)
                    type_count += 1
                if len(records) >= quota or type_count >= target_per_type:
                    break
            if len(records) >= quota or type_count >= target_per_type:
                break
            total = int(data.get("total") or 0)
            if not posts or page * 10 >= total:
                break
            page += 1
    # Fill any remainder with social posts because that source has the deepest pool.
    page = 1
    while len(records) < quota and page <= 50:
        response = fetcher.request(
            source_id,
            f"list-social-fill-{page}",
            "POST",
            url,
            data={
                "recruitType": "SOCIAL",
                "pageSize": "10",
                "keyWord": keyword,
                "curPage": str(page),
                "projectType": "",
            },
            headers={"Referer": "https://talent.baidu.com/jobs/social-list"},
        )
        payload = _json_payload(response, source_id)
        data = payload.get("data") or {}
        posts = data.get("list") or []
        for post in posts:
            external_id = str(post.get("postId") or post.get("jobId") or "").strip()
            if not external_id or external_id in seen:
                continue
            record = _record(
                source_id=source_id,
                external_id=external_id,
                title=post.get("name"),
                company=COMPANIES[source_id],
                region=post.get("workPlace"),
                industry="互联网/人工智能",
                responsibilities=post.get("workContent"),
                requirements=post.get("serviceCondition"),
                url=f"https://talent.baidu.com/jobs/detail/SOCIAL/{external_id}",
                published_at=_iso_date(post.get("publishDate")),
                updated_at=_iso_date(post.get("updateDate")),
                collected_at=collected_at,
                snapshot_week=snapshot_week,
                extra={"employment_type": "social", "job_type": post.get("postType")},
            )
            if _valid_full_record(record) and _is_ai_record(
                record["job_title"], record["responsibilities"], record["requirements"]
            ):
                records.append(record)
                seen.add(external_id)
            if len(records) >= quota:
                break
        if not posts:
            break
        page += 1
    return SourceResult(source_id, tuple(records))


def _collect_huawei(
    fetcher: AuditedFetcher,
    *,
    quota: int,
    keyword: str,
    collected_at: datetime,
    snapshot_week: str,
) -> SourceResult:
    del keyword  # Huawei's official AI landing page is already the explicit filter.
    source_id = "huawei"
    listing_url = "https://career.huawei.com/reccampportal/portal5/social-recruitment-ai.html"
    response = fetcher.request(source_id, "ai-list", "GET", listing_url)
    soup = BeautifulSoup(response.content, "html.parser")
    identifiers: list[tuple[str, str]] = []
    for link in soup.select('a[href*="social-recruitment-detail"]'):
        query = parse_qs(urlsplit(urljoin(listing_url, str(link.get("href")))).query)
        job_id = str((query.get("jobId") or [""])[0]).strip()
        data_source = str((query.get("dataSource") or ["1"])[0]).strip() or "1"
        if job_id and (job_id, data_source) not in identifiers:
            identifiers.append((job_id, data_source))

    records: list[dict[str, Any]] = []
    for job_id, data_source in identifiers[:quota]:
        api = (
            "https://career.huawei.com/reccampportal/services/portal/portalpub/"
            "getJobDetail/newHr"
        )
        detail_page = (
            "https://career.huawei.com/reccampportal/portal5/social-recruitment-detail.html?"
            + urlencode({"jobId": job_id, "dataSource": data_source})
        )
        response = fetcher.request(
            source_id,
            f"detail-{job_id}",
            "GET",
            api,
            params={"jobId": job_id, "dataSource": data_source},
            headers={"Referer": detail_page},
        )
        detail = _json_payload(response, source_id)
        record = _record(
            source_id=source_id,
            external_id=job_id,
            title=detail.get("jobname") or detail.get("externalJobName"),
            company=COMPANIES[source_id],
            region=detail.get("jobArea") or detail.get("jobAddress"),
            industry="信息通信/人工智能",
            responsibilities=detail.get("mainBusiness") or detail.get("jobDesc"),
            requirements=detail.get("jobRequire"),
            url=detail_page,
            published_at=_iso_datetime_date(detail.get("issuanceStartDate")),
            updated_at=_iso_datetime_date(detail.get("lastUpdateDate")),
            collected_at=collected_at,
            snapshot_week=snapshot_week,
            extra={
                "department": detail.get("deptName"),
                "job_family": detail.get("jobFamilyName"),
                "job_code": detail.get("jobCode"),
                "data_source": detail.get("dataSource"),
            },
        )
        if _valid_full_record(record) and _is_ai_record(
            record["job_title"], record["responsibilities"], record["requirements"]
        ):
            records.append(record)
    return SourceResult(source_id, tuple(records))


def _record(
    *,
    source_id: str,
    external_id: str,
    title: Any,
    company: str,
    region: Any,
    industry: str,
    responsibilities: Any,
    requirements: Any,
    url: Any,
    published_at: str | None,
    updated_at: str | None,
    collected_at: datetime,
    snapshot_week: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_title = _clean_text(title)
    clean_responsibilities = _clean_text(responsibilities)
    clean_requirements = _clean_text(requirements)
    clean_url = _canonical_url(_clean_text(url))
    text = f"岗位职责：\n{clean_responsibilities}\n\n岗位要求：\n{clean_requirements}".strip()
    content_sha256 = sha256_text(text)
    document_id = stable_id("eval-doc", source_id, external_id)
    return {
        "schema_version": "public_eval_jd_v1",
        "document_id": document_id,
        "source_id": source_id,
        "source_name": SOURCE_NAMES[source_id],
        "source_domain": SOURCE_DOMAINS[source_id],
        "external_id": str(external_id),
        "job_id": str(external_id),
        "job_title": clean_title,
        "company_name": company,
        "industry": industry,
        "location": _clean_text(region),
        "responsibilities": clean_responsibilities,
        "requirements": clean_requirements,
        "jd_text": text,
        "url": clean_url,
        "publish_date": published_at,
        "updated_at": updated_at,
        "collected_at": collected_at.isoformat(),
        "scrape_time": collected_at.isoformat(),
        "snapshot_id": f"{collected_at.date().isoformat()}:{source_id}-careers",
        "snapshot_week": snapshot_week,
        "content_sha256": content_sha256,
        "license": "source-reference-only",
        "redistribution_allowed": False,
        "collector_version": COLLECTOR_VERSION,
        "metadata": _drop_empty(dict(extra or {})),
    }


def _valid_full_record(record: Mapping[str, Any]) -> bool:
    return bool(
        str(record.get("external_id") or "").strip()
        and str(record.get("job_title") or "").strip()
        and len(str(record.get("responsibilities") or "").strip()) >= 30
        and len(str(record.get("requirements") or "").strip()) >= 20
        and str(record.get("url") or "").startswith("https://")
    )


def _is_ai_record(*values: Any) -> bool:
    text = " ".join(_clean_text(value) for value in values).casefold()
    return any(term in text for term in _AI_TERMS)


def _reference_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "public_eval_jd_reference_v1",
        "document_id": record["document_id"],
        "source_id": record["source_id"],
        "source_domain": record["source_domain"],
        "external_id": record["external_id"],
        "job_title": record["job_title"],
        "company_name": record["company_name"],
        "location": record["location"],
        "url": record["url"],
        "publish_date": record.get("publish_date"),
        "updated_at": record.get("updated_at"),
        "collected_at": record["collected_at"],
        "snapshot_id": record["snapshot_id"],
        "snapshot_week": record["snapshot_week"],
        "content_sha256": record["content_sha256"],
        "content_chars": len(str(record["jd_text"])),
        "license": "source-reference-only",
        "redistribution_allowed": False,
    }


def _build_source_manifest(
    results: Sequence[SourceResult],
    root: Path,
    collected_at: datetime,
    snapshot_week: str,
) -> dict[str, Any]:
    sources = []
    manifest_dir = root / "private"
    for result in results:
        if not result.records:
            continue
        job_file = manifest_dir / "jobs" / f"{result.source_id}.jsonl"
        sources.append(
            {
                "source_id": f"{result.source_id}-careers-{collected_at.date().isoformat()}",
                "source_type": "job",
                "input": job_file.relative_to(manifest_dir).as_posix(),
                "input_format": "jsonl",
                "source_name": SOURCE_NAMES[result.source_id],
                "publisher": COMPANIES[result.source_id],
                "collected_at": collected_at.isoformat(),
                "license": "source-reference-only",
                "metadata": {
                    "snapshot_id": f"{collected_at.date().isoformat()}:{result.source_id}-careers",
                    "snapshot_week": snapshot_week,
                    "source_domain": SOURCE_DOMAINS[result.source_id],
                    "redistribution_allowed": False,
                },
            }
        )
    return {"schema_version": "source_manifest_v1", "sources": sources}


def _snapshot_rows(
    results: Sequence[SourceResult],
    request_log: Sequence[Mapping[str, Any]],
    robots_rows: Sequence[Mapping[str, Any]],
    collected_at: datetime,
    snapshot_week: str,
    raw_root: Path,
) -> list[dict[str, Any]]:
    robots_by_source = {str(row["source_id"]): row for row in robots_rows}
    rows: list[dict[str, Any]] = []
    for result in results:
        requests = [row for row in request_log if row.get("source_id") == result.source_id]
        raw_files = sorted(raw_root.glob(f"{result.source_id}/*"))
        bundle_seed = "\n".join(f"{path.name}:{sha256_file(path)}" for path in raw_files)
        rows.append(
            {
                "schema_version": "collection_snapshot_v1",
                "snapshot_id": f"{collected_at.date().isoformat()}:{result.source_id}-careers",
                "source_id": f"{result.source_id}-careers",
                "source_domain": SOURCE_DOMAINS[result.source_id],
                "collected_at": collected_at.isoformat(),
                "snapshot_week": snapshot_week,
                "raw_bundle_sha256": sha256_text(bundle_seed),
                "item_count": len(result.records),
                "http_success_count": sum(int(row.get("status_code") or 0) < 400 for row in requests),
                "http_failure_count": sum(int(row.get("status_code") or 0) >= 400 for row in requests),
                "robots_checked_at": robots_by_source.get(result.source_id, {}).get("checked_at"),
                "robots_decision": robots_by_source.get(result.source_id, {}).get("decision"),
                "license_or_terms_note": "source-reference-only; public page access is not redistribution permission",
                "valid_for_trend": False,
                "valid_for_cross_sectional_eval": bool(result.records),
                "status": result.status,
                "failure_reason": result.reason,
            }
        )
    return rows


def _deduplicate_external_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for record in sorted(records, key=lambda row: (row["source_id"], row["external_id"])):
        selected.setdefault((record["source_id"], record["external_id"]), record)
    return list(selected.values())


def _json_payload(response: httpx.Response, source_id: str) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise ValueError(f"{source_id}: expected JSON response") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{source_id}: expected JSON object response")
    return value


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    scheme = "https" if parts.scheme in {"http", "https"} else parts.scheme
    host = (parts.hostname or "").casefold()
    port = parts.port
    netloc = host if port is None or (scheme == "https" and port == 443) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = "/".join(str(item) for item in value if item is not None)
    raw = str(value)
    text = (
        BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
        if re.search(r"<[^>]+>", raw)
        else raw
    )
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _parse_chinese_date(value: Any) -> str | None:
    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(value or ""))
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()


def _iso_date(value: Any) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else None


def _iso_datetime_date(value: Any) -> str | None:
    return _iso_date(value)


def _milliseconds_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


def _target_paths(source_id: str) -> tuple[str, ...]:
    return {
        "tencent": ("/tencentcareer/api/post/Query", "/tencentcareer/api/post/ByPostId"),
        "meituan": ("/api/official/job/getJobList",),
        "xiaomi": ("/website/api/agent/searchJobPage",),
        "baidu": ("/httservice/getPostListNew",),
        "huawei": (
            "/reccampportal/portal5/social-recruitment-ai.html",
            "/reccampportal/services/portal/portalpub/getJobDetail/newHr",
        ),
    }[source_id]


__all__ = [
    "AuditedFetcher",
    "CollectionStopped",
    "DEFAULT_QUOTAS",
    "SourceResult",
    "build_annotation_templates",
    "collect_public_evaluation_snapshot",
    "inspect_robots",
    "summarize_authoritative_corpus",
    "validate_evaluation_snapshot",
]
