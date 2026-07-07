#!/usr/bin/env python3
"""Fill domestic Zhaopin AI/ML technical JD data to a target size."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APPEND_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
REBUILD_PATH = REPO_ROOT / "scripts" / "rebuild_strong_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"


EXTRA_KEYWORDS = [
    "AI工程师",
    "人工智能工程师",
    "人工智能算法",
    "人工智能研发",
    "AI开发工程师",
    "AI应用开发",
    "大模型开发工程师",
    "大模型应用开发",
    "大模型算法工程师",
    "大模型工程师",
    "大模型研发工程师",
    "大语言模型",
    "LLM工程师",
    "LLM算法",
    "NLP算法工程师",
    "自然语言处理工程师",
    "机器学习工程师",
    "机器学习算法",
    "深度学习工程师",
    "深度学习算法",
    "计算机视觉工程师",
    "机器视觉工程师",
    "视觉算法工程师",
    "图像算法工程师",
    "目标检测",
    "多模态算法工程师",
    "推荐算法工程师",
    "搜索算法工程师",
    "知识图谱工程师",
    "语音识别工程师",
    "强化学习工程师",
    "AIGC算法工程师",
    "智能体开发",
    "Agent开发工程师",
    "RAG开发工程师",
    "模型部署工程师",
    "模型推理工程师",
    "算法研究员",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=3000)
    parser.add_argument("--max-page", type=int, default=120)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--recent-since", default="2024-07-06")
    args = parser.parse_args()

    helper = load_module(APPEND_PATH, "append_ai_jd_data_fill")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_fill")
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    rows, stats = collect_from_existing_and_cache(helper, rebuild, scrape_time)
    print(json.dumps({"stage": "initial", "rows": len(rows), "stats": stats}, ensure_ascii=False), flush=True)

    seen = {str(row.get("job_id")) for row in rows if row.get("job_id") is not None}
    tasks = build_missing_tasks(helper, args.max_page)
    fetched_pages = 0
    parsed_pages = 0
    positions_seen = 0
    added = 0
    weak_skipped = 0
    duplicate_skipped = 0

    batch_size = max(1, args.workers) * 3
    for start in range(0, len(tasks), batch_size):
        if len(rows) >= args.target_total:
            break
        batch = tasks[start : start + batch_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(fetch_task, helper, task): task for task in batch}
            for future in concurrent.futures.as_completed(futures):
                task = futures[future]
                fetched_pages += 1
                html = future.result()
                if not html:
                    continue
                items = helper.parse_positions(html)
                if not items:
                    continue
                parsed_pages += 1
                positions_seen += len(items)
                for item in items:
                    if len(rows) >= args.target_total:
                        break
                    job_id = item.get("jobId")
                    if job_id is None:
                        continue
                    key = str(job_id)
                    if key in seen:
                        duplicate_skipped += 1
                        continue
                    row = helper.convert_item(item, task, scrape_time)
                    if row.get("source_name") != "zhaopin" or not rebuild.is_strong_ai_ml_related(row):
                        weak_skipped += 1
                        continue
                    rows.append(row)
                    seen.add(key)
                    added += 1
                if fetched_pages % 50 == 0 or len(rows) >= args.target_total:
                    print(
                        json.dumps(
                            {
                                "stage": "fetch",
                                "rows": len(rows),
                                "target": args.target_total,
                                "fetched_pages": fetched_pages,
                                "parsed_pages": parsed_pages,
                                "positions_seen": positions_seen,
                                "added": added,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                if len(rows) >= args.target_total:
                    break

    if len(rows) < args.target_total:
        raise SystemExit(
            json.dumps(
                {
                    "status": "insufficient_domestic_strong_ai_ml_rows",
                    "collected": len(rows),
                    "target_total": args.target_total,
                    "fetched_pages": fetched_pages,
                    "parsed_pages": parsed_pages,
                    "positions_seen": positions_seen,
                    "added": added,
                    "weak_skipped": weak_skipped,
                    "duplicate_skipped": duplicate_skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rebuild.sort_rows(rows[: args.target_total])
    write_jsonl(JD_JSONL, rows)
    write_csv(JD_CSV, rows, helper.CSV_FIELDS)
    write_summary(
        rows=rows,
        scrape_time=scrape_time,
        keywords=sorted(set([*rebuild.STRONG_KEYWORDS, *EXTRA_KEYWORDS])),
        cities=list(helper.CITIES.values()),
        stats={
            **stats,
            "fetched_pages": fetched_pages,
            "parsed_pages": parsed_pages,
            "positions_seen": positions_seen,
            "added_after_initial": added,
            "weak_skipped_after_initial": weak_skipped,
            "duplicate_skipped_after_initial": duplicate_skipped,
        },
        recent_since=args.recent_since,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "total_after": len(rows),
                "source_counts": source_counts(rows),
                "first_title": rows[0].get("job_title"),
                "last_title": rows[-1].get("job_title"),
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


def collect_from_existing_and_cache(helper: Any, rebuild: Any, scrape_time: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {
        "existing_total": 0,
        "existing_kept": 0,
        "foreign_skipped": 0,
        "existing_weak_skipped": 0,
        "cache_pages": 0,
        "cache_pages_parsed": 0,
        "cache_positions_seen": 0,
        "cache_added": 0,
        "cache_duplicate_skipped": 0,
        "cache_weak_skipped": 0,
    }
    if JD_JSONL.exists():
        for line in JD_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            stats["existing_total"] += 1
            row = json.loads(line)
            if row.get("source_name") != "zhaopin":
                stats["foreign_skipped"] += 1
                continue
            key = str(row.get("job_id") or row.get("url") or "")
            if key in seen:
                stats["cache_duplicate_skipped"] += 1
                continue
            if rebuild.is_strong_ai_ml_related(row):
                rows.append(row)
                seen.add(key)
                stats["existing_kept"] += 1
            else:
                stats["existing_weak_skipped"] += 1

    for path in sorted(helper.FETCH_ROOT.glob("*.html")):
        task = task_from_cache_name(helper, path)
        if task is None:
            continue
        stats["cache_pages"] += 1
        html = path.read_text(encoding="utf-8", errors="replace")
        items = helper.parse_positions(html)
        if not items:
            continue
        stats["cache_pages_parsed"] += 1
        stats["cache_positions_seen"] += len(items)
        for item in items:
            job_id = item.get("jobId")
            if job_id is None:
                continue
            key = str(job_id)
            if key in seen:
                stats["cache_duplicate_skipped"] += 1
                continue
            row = helper.convert_item(item, task, scrape_time)
            if row.get("source_name") != "zhaopin" or not rebuild.is_strong_ai_ml_related(row):
                stats["cache_weak_skipped"] += 1
                continue
            rows.append(row)
            seen.add(key)
            stats["cache_added"] += 1
    return rows, stats


def build_missing_tasks(helper: Any, max_page: int) -> list[Any]:
    keywords = sorted(set([*getattr(helper, "KEYWORDS"), *EXTRA_KEYWORDS]))
    tasks = []
    for page in range(1, max_page + 1):
        for keyword in keywords:
            for city_code, city_name in helper.CITIES.items():
                task = helper.FetchTask(keyword=keyword, city_code=city_code, city_name=city_name, page=page)
                if not task.cache_path.exists():
                    tasks.append(task)
    return tasks


def task_from_cache_name(helper: Any, path: Path) -> Any | None:
    import re

    match = re.match(r"(?P<city>\d+)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
    if not match:
        return None
    city_code = match.group("city")
    return helper.FetchTask(
        keyword=match.group("keyword"),
        city_code=city_code,
        city_name=helper.CITIES.get(city_code, city_code),
        page=int(match.group("page")),
    )


def fetch_task(helper: Any, task: Any) -> str:
    if task.cache_path.exists():
        return task.cache_path.read_text(encoding="utf-8", errors="replace")
    ps_command = (
        "$ProgressPreference='SilentlyContinue'; "
        f"$uri='{task.url}'; "
        "$headers=@{"
        "'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36';"
        "'Accept-Language'='zh-CN,zh;q=0.9';"
        "'Referer'='https://sou.zhaopin.com/'"
        "}; "
        "(Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $headers).Content"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    except Exception:
        return ""
    task.cache_path.parent.mkdir(parents=True, exist_ok=True)
    task.cache_path.write_text(completed.stdout, encoding="utf-8")
    time.sleep(0.01)
    return completed.stdout


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
                output[key] = json.dumps(output[key] if isinstance(output[key], list) else [], ensure_ascii=False)
            writer.writerow(output)


def write_summary(
    *,
    rows: list[dict[str, Any]],
    scrape_time: str,
    keywords: list[str],
    cities: list[str],
    stats: dict[str, int],
    recent_since: str,
) -> None:
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    summary.update(
        {
            "source": "zhaopin",
            "keyword": "domestic strong AI/ML technical jobs only; sorted by job_title",
            "deduped": len({str(row.get("job_id")) for row in rows}),
            "saved": len(rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
            "source_counts": source_counts(rows),
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page",
        "topic": "domestic strong AI/ML technical jobs only",
        "keywords": keywords,
        "cities": cities,
        "recent_since": recent_since,
        "total_after": len(rows),
        "scrape_time": scrape_time,
        "sort": "job_title, company_name, location, job_id",
        "stats": stats,
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source_name") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
