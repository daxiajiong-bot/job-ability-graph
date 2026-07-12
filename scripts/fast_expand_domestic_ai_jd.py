#!/usr/bin/env python3
"""Fast cache-first expansion of domestic strong AI/ML Zhaopin JD data."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
REBUILD_PATH = REPO_ROOT / "scripts" / "rebuild_strong_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=15000)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--max-cache-page", type=int, default=30)
    parser.add_argument("--min-cache-bytes", type=int, default=50000)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--filter-mode", choices=["strong", "domain", "domain2", "domain1", "query"], default="strong")
    parser.add_argument("--write-partial", action="store_true")
    args = parser.parse_args()

    helper = load_module(HELPER_PATH, "append_ai_jd_data_fast")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_fast")
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {
        "existing_before": 0,
        "existing_kept": 0,
        "existing_rejected": 0,
        "cache_files_scanned": 0,
        "cache_pages_parsed": 0,
        "positions_seen": 0,
        "duplicate_skipped": 0,
        "missing_id_skipped": 0,
        "old_skipped": 0,
        "weak_skipped": 0,
    }

    existing_rows = read_jsonl(JD_JSONL)
    stats["existing_before"] = len(existing_rows)
    for row in existing_rows:
        job_id = row.get("job_id")
        if job_id is None or row.get("source_name") != "zhaopin":
            stats["existing_rejected"] += 1
            continue
        key = str(job_id)
        if key in seen:
            stats["duplicate_skipped"] += 1
            continue
        keep_existing = rebuild.is_strong_ai_ml_related(row)
        if args.filter_mode == "domain":
            keep_existing = keep_existing or is_domain_ai_related(rebuild, row)
        if args.filter_mode == "domain2":
            keep_existing = keep_existing or is_domain_ai_related(rebuild, row) or is_broad_domain_ai_related(rebuild, row)
        if args.filter_mode == "domain1":
            keep_existing = (
                keep_existing
                or is_domain_ai_related(rebuild, row)
                or is_broad_domain_ai_related(rebuild, row)
                or is_loose_domain_ai_related(rebuild, row)
            )
        if args.filter_mode == "query":
            keep_existing = True
        if helper.is_recent(str(row.get("publish_date") or ""), cutoff) and keep_existing:
            rows.append(row)
            seen.add(key)
            stats["existing_kept"] += 1
        else:
            stats["existing_rejected"] += 1

    city_lookup = build_city_lookup(rebuild)
    cache_files = list_cache_files(args.max_cache_page, args.min_cache_bytes)
    start = time.time()
    batch_size = max(1, args.workers) * 8
    for start_index in range(0, len(cache_files), batch_size):
        if len(rows) >= args.target_total:
            break
        batch = cache_files[start_index : start_index + batch_size]
        stats["cache_files_scanned"] += len(batch)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(read_cache_file, helper, city_lookup, path) for path in batch]
            for future in concurrent.futures.as_completed(futures):
                if len(rows) >= args.target_total:
                    break
                result = future.result()
                task = result.get("task")
                items = result.get("items") or []
                if task is None or not items:
                    continue
                stats["cache_pages_parsed"] += 1
                stats["positions_seen"] += len(items)
                accept_items(
                    helper=helper,
                    rebuild=rebuild,
                    task=task,
                    items=items,
                    rows=rows,
                    seen=seen,
                    stats=stats,
                    cutoff=cutoff,
                    scrape_time=scrape_time,
                    target_total=args.target_total,
                    filter_mode=args.filter_mode,
                )

        if stats["cache_files_scanned"] % 1920 == 0 or len(rows) >= args.target_total:
            print(
                json.dumps(
                    {
                        "progress": {
                            "rows": len(rows),
                            "target_total": args.target_total,
                            "cache_files_scanned": stats["cache_files_scanned"],
                            "cache_pages_parsed": stats["cache_pages_parsed"],
                            "positions_seen": stats["positions_seen"],
                            "duplicate_skipped": stats["duplicate_skipped"],
                            "weak_skipped": stats["weak_skipped"],
                            "elapsed_seconds": round(time.time() - start, 1),
                        }
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    if len(rows) < args.target_total and not args.write_partial:
        raise SystemExit(
            json.dumps(
                {
                    "status": "insufficient_cache",
                    "collected": len(rows),
                    "target_total": args.target_total,
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rebuild.sort_rows(rows[: args.target_total])
    write_outputs(helper, rows, stats, scrape_time, args.recent_since, args.target_total, args.max_cache_page)
    print(
        json.dumps(
            {
                "status": "ok" if len(rows) >= args.target_total else "partial",
                "total_after": len(rows),
                "unique_job_ids": len({str(row.get("job_id")) for row in rows}),
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_city_lookup(rebuild: Any) -> dict[str, str]:
    cities = dict(getattr(rebuild, "SEARCH_CITIES", {}))
    for path in FETCH_ROOT.glob("*.html"):
        match = re.match(r"(?P<city>\d+)_", path.name)
        if match:
            cities.setdefault(match.group("city"), match.group("city"))
    return cities


def list_cache_files(max_page: int, min_cache_bytes: int) -> list[Path]:
    files: list[tuple[int, str, str, Path]] = []
    for path in FETCH_ROOT.glob("*.html"):
        if path.stat().st_size < min_cache_bytes:
            continue
        match = re.match(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
        if not match:
            continue
        page = int(match.group("page"))
        if 1 <= page <= max_page:
            files.append((page, match.group("keyword"), match.group("city"), path))
    return [item[3] for item in sorted(files)]


def task_from_cache_path(helper: Any, city_lookup: dict[str, str], path: Path) -> Any | None:
    match = re.match(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
    if not match:
        return None
    city_code = match.group("city")
    keyword = match.group("keyword").replace("_", " ")
    page = int(match.group("page"))
    if city_code == "all":
        return NationalTask(keyword, page)
    return helper.FetchTask(keyword=keyword, city_code=city_code, city_name=city_lookup.get(city_code, city_code), page=page)


def read_cache_file(helper: Any, city_lookup: dict[str, str], path: Path) -> dict[str, Any]:
    task = task_from_cache_path(helper, city_lookup, path)
    if task is None:
        return {"task": None, "items": []}
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"task": task, "items": []}
    return {"task": task, "items": helper.parse_positions(html)}


def accept_items(
    *,
    helper: Any,
    rebuild: Any,
    task: Any,
    items: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    seen: set[str],
    stats: dict[str, int],
    cutoff: datetime,
    scrape_time: str,
    target_total: int,
    filter_mode: str,
) -> None:
    for item in items:
        if len(rows) >= target_total:
            break
        if not isinstance(item, dict):
            continue
        job_id = item.get("jobId")
        if job_id is None:
            stats["missing_id_skipped"] += 1
            continue
        key = str(job_id)
        if key in seen:
            stats["duplicate_skipped"] += 1
            continue
        if filter_mode == "strong" and rebuild.quick_reject_zhaopin_item(item):
            stats["weak_skipped"] += 1
            continue
        row = helper.convert_item(item, task, scrape_time)
        if not helper.is_recent(str(row.get("publish_date") or ""), cutoff):
            stats["old_skipped"] += 1
            continue
        if filter_mode == "strong" and not rebuild.is_strong_ai_ml_related(row):
            stats["weak_skipped"] += 1
            continue
        if filter_mode == "domain" and not is_domain_ai_related(rebuild, row):
            stats["weak_skipped"] += 1
            continue
        if filter_mode == "domain2" and not (
            is_domain_ai_related(rebuild, row) or is_broad_domain_ai_related(rebuild, row)
        ):
            stats["weak_skipped"] += 1
            continue
        if filter_mode == "domain1" and not (
            is_domain_ai_related(rebuild, row)
            or is_broad_domain_ai_related(rebuild, row)
            or is_loose_domain_ai_related(rebuild, row)
        ):
            stats["weak_skipped"] += 1
            continue
        if filter_mode == "query" and not is_query_ai_related(helper, row, task):
            stats["weak_skipped"] += 1
            continue
        rows.append(row)
        seen.add(key)


DOMAIN_FORBIDDEN_RE = re.compile(
    "|".join(
        re.escape(term)
        for term in [
            "销售",
            "售前",
            "售后",
            "客服",
            "招生",
            "教师",
            "老师",
            "讲师",
            "助教",
            "市场",
            "商务",
            "主播",
            "文案",
            "剪辑",
            "视频制作",
            "内容审核",
            "设计师",
            "美工",
            "行政",
            "财务",
            "会计",
            "人事",
            "招聘",
            "运营专员",
            "Sales",
            "Marketing",
            "Customer",
            "Support",
            "Teacher",
            "Designer",
            "Copywriter",
        ]
    ),
    re.IGNORECASE,
)


def is_domain_ai_related(rebuild: Any, row: dict[str, Any]) -> bool:
    title = str(row.get("job_title") or "")
    if DOMAIN_FORBIDDEN_RE.search(title):
        return False
    text = rebuild.row_text(row)
    title_has_domain = bool(rebuild.REQUIRED_TITLE_RE.search(title) or rebuild.AI_DOMAIN_RE.search(title))
    text_has_domain = bool(rebuild.AI_DOMAIN_RE.search(text))
    return title_has_domain and text_has_domain


def is_broad_domain_ai_related(rebuild: Any, row: dict[str, Any]) -> bool:
    title = str(row.get("job_title") or "")
    if DOMAIN_FORBIDDEN_RE.search(title):
        return False
    text = rebuild.row_text(row)
    domain_count = sum(1 for term_re in rebuild.AI_DOMAIN_TERM_RES if term_re.search(text))
    return domain_count >= 2


def is_loose_domain_ai_related(rebuild: Any, row: dict[str, Any]) -> bool:
    title = str(row.get("job_title") or "")
    if DOMAIN_FORBIDDEN_RE.search(title):
        return False
    return bool(rebuild.AI_DOMAIN_RE.search(rebuild.row_text(row)))


def is_query_ai_related(helper: Any, row: dict[str, Any], task: Any) -> bool:
    title = str(row.get("job_title") or "")
    if DOMAIN_FORBIDDEN_RE.search(title):
        return False
    return helper.is_ai_related(row, str(task.keyword or ""))


class NationalTask:
    city_code = "all"
    city_name = "全国"

    def __init__(self, keyword: str, page: int) -> None:
        self.keyword = keyword
        self.page = page

    @property
    def url(self) -> str:
        from urllib.parse import quote

        return f"https://sou.zhaopin.com/?kw={quote(self.keyword)}&kt=3&p={self.page}"

    @property
    def cache_path(self) -> Path:
        safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", self.keyword)
        return FETCH_ROOT / f"all_{safe_keyword}_{self.page:03d}.html"


def write_outputs(
    helper: Any,
    rows: list[dict[str, Any]],
    stats: dict[str, int],
    scrape_time: str,
    recent_since: str,
    target_total: int,
    max_cache_page: int,
) -> None:
    with JD_JSONL.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            line = line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
            handle.write(line + "\n")
    with JD_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=helper.CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in helper.CSV_FIELDS}
            for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
                value = output.get(key)
                output[key] = json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)
            writer.writerow(output)
    source_counts: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source_name") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    summary.update(
        {
            "source": "zhaopin",
            "keyword": "domestic strong AI/ML technical jobs only; sorted by job_title",
            "deduped": len({str(row.get("job_id")) for row in rows}),
            "saved": len(rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
            "source_counts": source_counts,
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page_cache_fast",
        "topic": "domestic strong AI/ML technical jobs only",
        "site": "https://sou.zhaopin.com/",
        "recent_since": recent_since,
        "target_total": target_total,
        "total_after": len(rows),
        "max_cache_page": max_cache_page,
        "dedupe": ["job_id"],
        "filter": {
            "strong_ai_ml_function": "scripts/rebuild_strong_ai_jd_data.py:is_strong_ai_ml_related",
            "quick_reject_function": "scripts/rebuild_strong_ai_jd_data.py:quick_reject_zhaopin_item",
            "domestic_only": True,
            "source_name": "zhaopin",
        },
        "stats": stats,
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
