#!/usr/bin/env python3
"""Refill jd_raw outputs from long-tail Zhaopin cache files only.

This is a targeted companion to refill_title_ai_jd_data.py. It reuses the same
AI-related technical-role filter, but avoids rescanning every cached Zhaopin
HTML file when only newly expanded long-tail cache pages need to be screened.
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
REFILL_PATH = REPO_ROOT / "scripts" / "refill_title_ai_jd_data.py"
EXPAND_PATH = REPO_ROOT / "scripts" / "expand_zhaopin_cache.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-total", type=int, default=15000)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--max-cache-page", type=int, default=60)
    parser.add_argument("--min-cache-bytes", type=int, default=1)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--write-partial", action="store_true")
    parser.add_argument(
        "--modified-since",
        default="",
        help="Optional local datetime like 2026-07-14T18:00:00; only cache files modified after this time.",
    )
    args = parser.parse_args()

    helper = load_module(HELPER_PATH, "append_ai_jd_data_longtail_refill")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_longtail_refill")
    refill = load_module(REFILL_PATH, "refill_title_ai_jd_data_longtail_refill")
    expand = load_module(EXPAND_PATH, "expand_zhaopin_cache_longtail_refill")
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    modified_since = parse_local_datetime(args.modified_since)

    stats = initial_stats()
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()

    existing_rows = refill.read_jsonl(JD_JSONL)
    stats["existing_before"] = len(existing_rows)
    for row in existing_rows:
        reason = refill.rejection_reason(row, cutoff, rebuild)
        if row.get("source_name") != "zhaopin":
            stats["existing_removed_non_zhaopin"] += 1
            continue
        job_id = row.get("job_id")
        key = str(job_id) if job_id is not None else ""
        if not key or key in seen_ids:
            stats["existing_removed_duplicate_id"] += 1
            continue
        signature = refill.row_signature(row)
        if reason:
            stats[f"existing_removed_{reason}"] = stats.get(f"existing_removed_{reason}", 0) + 1
            continue
        rows.append(row)
        seen_ids.add(key)
        seen_signatures.add(signature)
        stats["existing_kept"] += 1
        tier = refill.accepted_row_match_tier(row, rebuild)
        stats[f"existing_kept_{tier}_title"] = stats.get(f"existing_kept_{tier}_title", 0) + 1

    cache_files = list_longtail_cache_files(
        longtail_keywords=getattr(expand, "REFILL_KEYWORDS", getattr(expand, "LONGTAIL_KEYWORDS", [])),
        max_page=args.max_cache_page,
        min_cache_bytes=args.min_cache_bytes,
        modified_since=modified_since,
    )
    print(
        json.dumps(
            {
                "plan": {
                    "existing_kept": len(rows),
                    "target_total": args.target_total,
                    "cache_files": len(cache_files),
                    "max_cache_page": args.max_cache_page,
                    "min_cache_bytes": args.min_cache_bytes,
                    "modified_since": args.modified_since,
                }
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    start = time.time()
    batch_size = max(1, args.workers) * 8
    for index in range(0, len(cache_files), batch_size):
        if len(rows) >= args.target_total:
            break
        batch = cache_files[index : index + batch_size]
        stats["cache_files_scanned"] += len(batch)
        known_ids = frozenset(seen_ids)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(refill.read_cache_file, helper, path, known_ids) for path in batch]
            for future in concurrent.futures.as_completed(futures):
                if len(rows) >= args.target_total:
                    break
                task, items = future.result()
                if task is None or not items:
                    continue
                stats["cache_pages_parsed"] += 1
                stats["positions_seen"] += len(items)
                refill.accept_items(
                    helper=helper,
                    rebuild=rebuild,
                    task=task,
                    items=items,
                    rows=rows,
                    seen_ids=seen_ids,
                    seen_signatures=seen_signatures,
                    stats=stats,
                    cutoff=cutoff,
                    scrape_time=scrape_time,
                    target_total=args.target_total,
                    dedupe_signature=False,
                )
        print(
            json.dumps(
                {
                    "progress": {
                        "rows": len(rows),
                        "target_total": args.target_total,
                        "cache_files_scanned": stats["cache_files_scanned"],
                        "cache_pages_parsed": stats["cache_pages_parsed"],
                        "positions_seen": stats["positions_seen"],
                        "added_from_cache": stats["added_from_cache"],
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
                    "status": "insufficient_longtail_cache",
                    "total_after": len(rows),
                    "target_total": args.target_total,
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rebuild.sort_rows(rows[: args.target_total])
    refill.write_outputs(refill.helper if hasattr(refill, "helper") else helper, rows, stats, scrape_time, args.recent_since, args.target_total, args.max_cache_page)
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


def initial_stats() -> dict[str, int]:
    return {
        "existing_before": 0,
        "existing_kept": 0,
        "existing_kept_strict_title": 0,
        "existing_kept_strong_synonym_title": 0,
        "existing_kept_text_strict_title": 0,
        "existing_kept_text_strong_synonym_title": 0,
        "existing_kept_high_confidence_title": 0,
        "existing_kept_related_technical_title": 0,
        "existing_removed_non_zhaopin": 0,
        "existing_removed_duplicate_id": 0,
        "existing_removed_duplicate_signature": 0,
        "existing_removed_no_title_keyword": 0,
        "existing_removed_not_strong_ai": 0,
        "existing_removed_weak_title": 0,
        "existing_removed_old": 0,
        "existing_removed_empty_jd_text": 0,
        "cache_files_scanned": 0,
        "cache_pages_parsed": 0,
        "positions_seen": 0,
        "added_from_cache": 0,
        "cache_added_strict_title": 0,
        "cache_added_strong_synonym_title": 0,
        "cache_added_text_strict_title": 0,
        "cache_added_text_strong_synonym_title": 0,
        "cache_added_high_confidence_title": 0,
        "cache_added_related_technical_title": 0,
        "cache_missing_id_skipped": 0,
        "cache_duplicate_id_skipped": 0,
        "cache_duplicate_signature_skipped": 0,
        "cache_no_title_keyword_skipped": 0,
        "cache_not_strong_ai_skipped": 0,
        "cache_weak_title_skipped": 0,
        "cache_old_skipped": 0,
        "cache_empty_jd_text_skipped": 0,
        "fetch_tasks_attempted": 0,
        "fetch_pages_parsed": 0,
        "fetch_positions_seen": 0,
        "added_from_fetch": 0,
        "dedupe_signature_enabled": 0,
    }


def list_longtail_cache_files(
    *,
    longtail_keywords: list[str],
    max_page: int,
    min_cache_bytes: int,
    modified_since: datetime | None,
) -> list[Path]:
    keywords = {sanitize_keyword(keyword) for keyword in longtail_keywords if str(keyword).strip()}
    pattern = re.compile(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$")
    files: list[tuple[int, float, str, Path]] = []
    for path in FETCH_ROOT.glob("*.html"):
        match = pattern.match(path.name)
        if not match:
            continue
        page = int(match.group("page"))
        if page < 1 or page > max_page:
            continue
        if path.stat().st_size < min_cache_bytes:
            continue
        if modified_since is not None:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime < modified_since:
                continue
        if match.group("keyword") not in keywords:
            continue
        files.append((page, -path.stat().st_size, path.name.casefold(), path))
    return [item[3] for item in sorted(files)]


def sanitize_keyword(keyword: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(keyword).strip())


def parse_local_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise SystemExit(f"invalid --modified-since: {value!r}")


if __name__ == "__main__":
    raise SystemExit(main())
