#!/usr/bin/env python3
"""Targeted refill from existing Zhaopin keyword/city cache coverage."""

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
REFILL_PATH = REPO_ROOT / "scripts" / "refill_title_ai_jd_data.py"
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
REBUILD_PATH = REPO_ROOT / "scripts" / "rebuild_strong_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=15000)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--prev-page", type=int, default=1)
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--min-prev-bytes", type=int, default=120000)
    parser.add_argument("--fetch-workers", type=int, default=12)
    parser.add_argument("--max-tasks", type=int, default=0)
    parser.add_argument("--mode", choices=["next-large", "cached-cities"], default="next-large")
    parser.add_argument("--write-partial", action="store_true")
    args = parser.parse_args()

    helper = load_module(HELPER_PATH, "append_ai_jd_data_targeted_refill")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_targeted_refill")
    refill = load_module(REFILL_PATH, "refill_title_ai_jd_data_targeted_refill")
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    rows = []
    seen_ids = set()
    seen_signatures = set()
    for row in refill.read_jsonl(JD_JSONL):
        reason = refill.rejection_reason(row, cutoff, rebuild)
        job_id = row.get("job_id")
        key = str(job_id) if job_id is not None else ""
        if row.get("source_name") != "zhaopin" or not key or key in seen_ids or reason:
            continue
        rows.append(row)
        seen_ids.add(key)
        seen_signatures.add(refill.row_signature(row))

    stats: dict[str, int] = {
        "existing_before": len(rows),
        "existing_kept": len(rows),
        "existing_kept_strict_title": 0,
        "existing_kept_strong_synonym_title": 0,
        "existing_kept_text_strict_title": 0,
        "existing_kept_text_strong_synonym_title": 0,
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
    for row in rows:
        tier = refill.accepted_row_match_tier(row, rebuild)
        stats[f"existing_kept_{tier}_title"] = stats.get(f"existing_kept_{tier}_title", 0) + 1

    if args.mode == "cached-cities":
        tasks = list_cached_city_tasks(refill, rebuild, args.page or args.prev_page)
    else:
        next_page = args.prev_page + 1
        tasks = list_target_tasks(refill, args.prev_page, next_page, args.min_prev_bytes)
    if args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]

    start = time.time()
    batch_size = max(1, args.fetch_workers) * 4
    for index in range(0, len(tasks), batch_size):
        if len(rows) >= args.target_total:
            break
        batch = tasks[index : index + batch_size]
        stats["fetch_tasks_attempted"] += len(batch)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.fetch_workers)) as executor:
            futures = [executor.submit(refill.fetch_cache_file, rebuild, helper, task) for task in batch]
            for future in concurrent.futures.as_completed(futures):
                if len(rows) >= args.target_total:
                    break
                task, items = future.result()
                if task is None or not items:
                    continue
                stats["fetch_pages_parsed"] += 1
                stats["fetch_positions_seen"] += len(items)
                before = stats["added_from_cache"]
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
                stats["added_from_fetch"] += stats["added_from_cache"] - before
        if stats["fetch_tasks_attempted"] % 240 == 0 or len(rows) >= args.target_total:
            print(
                json.dumps(
                    {
                        "targeted_fetch_progress": {
                            "rows": len(rows),
                            "target_total": args.target_total,
                            "prev_page": args.prev_page,
                            "mode": args.mode,
                            "fetch_tasks_attempted": stats["fetch_tasks_attempted"],
                            "fetch_pages_parsed": stats["fetch_pages_parsed"],
                            "fetch_positions_seen": stats["fetch_positions_seen"],
                            "added_from_fetch": stats["added_from_fetch"],
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
                    "status": "insufficient_targeted_fetch",
                    "total_after": len(rows),
                    "target_total": args.target_total,
                    "tasks": len(tasks),
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rebuild.sort_rows(rows[: args.target_total])
    refill.write_outputs(helper, rows, stats, scrape_time, args.recent_since, args.target_total, 60)
    print(
        json.dumps(
            {
                "status": "ok" if len(rows) >= args.target_total else "partial",
                "total_after": len(rows),
                "unique_job_ids": len({str(row.get("job_id")) for row in rows}),
                "tasks": len(tasks),
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def list_target_tasks(refill: Any, prev_page: int, next_page: int, min_prev_bytes: int) -> list[Any]:
    tasks = []
    pattern = re.compile(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$")
    for path in sorted(FETCH_ROOT.glob(f"*_{prev_page:03d}.html"), key=lambda item: item.stat().st_size, reverse=True):
        if path.stat().st_size < min_prev_bytes:
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        city_code = match.group("city")
        keyword = match.group("keyword").replace("_", " ")
        task = refill.CacheTask(keyword=keyword, city_code=city_code, page=next_page)
        if task.cache_path.exists() and task.cache_path.stat().st_size >= 50000:
            continue
        tasks.append(task)
    return tasks


def list_cached_city_tasks(refill: Any, rebuild: Any, page: int) -> list[Any]:
    city_codes = discover_cached_city_codes()
    keywords = list(dict.fromkeys([*getattr(refill, "FETCH_KEYWORDS", []), *getattr(rebuild, "STRONG_KEYWORDS", [])]))
    tasks = []
    for keyword in keywords:
        for city_code in city_codes:
            task = refill.CacheTask(keyword=keyword, city_code=city_code, page=page)
            if task.cache_path.exists() and task.cache_path.stat().st_size >= 50000:
                continue
            tasks.append(task)
    return tasks


def discover_cached_city_codes() -> list[str]:
    codes = set()
    pattern = re.compile(r"(?P<city>\d+|all)_.+_\d+\.html$")
    for path in FETCH_ROOT.glob("*.html"):
        match = pattern.match(path.name)
        if match:
            codes.add(match.group("city"))
    return sorted(codes)


if __name__ == "__main__":
    raise SystemExit(main())
