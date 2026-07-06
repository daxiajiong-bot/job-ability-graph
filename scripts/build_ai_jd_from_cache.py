#!/usr/bin/env python3
"""Build JD raw data from cached AI/ML Zhaopin search pages."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"
BASE_COUNT = 0
AI_TERMS = [
    "人工智能",
    "机器学习",
    "深度学习",
    "算法",
    "大模型",
    "NLP",
    "自然语言",
    "计算机视觉",
    "图像",
    "推荐",
    "数据挖掘",
    "AIGC",
    "生成式",
    "AI",
    "PyTorch",
    "TensorFlow",
    "模型",
    "目标检测",
    "多模态",
    "LLM",
    "语音识别",
    "强化学习",
    "知识图谱",
    "视觉识别",
    "CV",
]
AI_RE = re.compile("|".join(re.escape(term) for term in AI_TERMS), re.IGNORECASE)


def load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("append_ai_jd_data", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load helper: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    helper = load_helper()
    target_total = 3000
    recent_since = "2024-07-06"
    cutoff = datetime.strptime(recent_since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    existing_rows = helper.read_jsonl(JD_JSONL)[:BASE_COUNT]
    existing_ids = {str(row.get("job_id")) for row in existing_rows if row.get("job_id") is not None}
    needed = target_total - len(existing_rows)
    if needed <= 0:
        print(json.dumps({"status": "already_complete", "total": len(existing_rows)}, ensure_ascii=False, indent=2))
        return 0

    added: list[dict[str, Any]] = []
    seen = set(existing_ids)
    stats = {
        "cache_files": 0,
        "parsed_pages": 0,
        "positions_seen": 0,
        "missing_id_skipped": 0,
        "duplicate_skipped": 0,
        "old_skipped": 0,
        "irrelevant_skipped": 0,
        "json_failed": 0,
    }
    task_samples: list[dict[str, Any]] = []

    for path in sorted(FETCH_ROOT.glob("*.html"), key=sort_key):
        stats["cache_files"] += 1
        task = task_from_path(path, helper)
        if task is None:
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        items = helper.parse_positions(html)
        if not items:
            continue
        stats["parsed_pages"] += 1
        stats["positions_seen"] += len(items)
        if len(task_samples) < 40:
            task_samples.append({"keyword": task.keyword, "city": task.city_name, "page": task.page})
        for item in items:
            if len(added) >= needed:
                break
            job_id = item.get("jobId") if isinstance(item, dict) else None
            if job_id is None:
                stats["missing_id_skipped"] += 1
                continue
            key = str(job_id)
            if key in seen:
                stats["duplicate_skipped"] += 1
                continue
            row = helper.convert_item(item, task, scrape_time)
            if not helper.is_recent(row["publish_date"], cutoff):
                stats["old_skipped"] += 1
                continue
            if not is_strict_ai_related(row):
                stats["irrelevant_skipped"] += 1
                continue
            seen.add(key)
            added.append(row)
        if len(added) % 500 == 0 and added:
            print(json.dumps({"progress_added": len(added), "last_file": path.name}, ensure_ascii=False), flush=True)
        if len(added) >= needed:
            break

    if len(added) < needed:
        raise SystemExit(
            json.dumps(
                {
                    "status": "insufficient_cache",
                    "needed": needed,
                    "added": len(added),
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    all_rows = [*existing_rows, *added]
    write_jsonl(JD_JSONL, all_rows)
    write_csv(JD_CSV, all_rows, helper.CSV_FIELDS)
    update_summary(
        helper=helper,
        existing_count=len(existing_rows),
        added=added,
        all_rows=all_rows,
        stats=stats,
        task_samples=task_samples,
        scrape_time=scrape_time,
        recent_since=recent_since,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "existing_before": len(existing_rows),
                "added": len(added),
                "total_after": len(all_rows),
                "unique_job_ids": len({str(row.get("job_id")) for row in all_rows}),
                "first_added_job_id": added[0]["job_id"],
                "last_added_job_id": added[-1]["job_id"],
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def sort_key(path: Path) -> tuple[int, str, int]:
    parsed = parse_cache_name(path)
    if parsed is None:
        return (999999, path.name, 999999)
    city_code, keyword, page = parsed
    return (page, keyword, int(city_code))


def task_from_path(path: Path, helper: Any) -> Any | None:
    parsed = parse_cache_name(path)
    if parsed is None:
        return None
    city_code, keyword, page = parsed
    return helper.FetchTask(
        keyword=keyword,
        city_code=city_code,
        city_name=helper.CITIES.get(city_code, city_code),
        page=page,
    )


def parse_cache_name(path: Path) -> tuple[str, str, int] | None:
    match = re.match(r"(?P<city>\d+)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
    if not match:
        return None
    return match.group("city"), match.group("keyword"), int(match.group("page"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            line = line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
            handle.write(line + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
                output[key] = json.dumps(output[key] if isinstance(output[key], list) else [], ensure_ascii=False)
            writer.writerow(output)


def is_strict_ai_related(row: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(row.get("job_title") or ""),
            str(row.get("industry") or ""),
            str(row.get("jd_text") or ""),
            " ".join(row.get("skills_raw") or []),
            " ".join(row.get("skills_norm") or []),
        ]
    )
    return bool(AI_RE.search(text))


def update_summary(
    *,
    helper: Any,
    existing_count: int,
    added: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    stats: dict[str, int],
    task_samples: list[dict[str, Any]],
    scrape_time: str,
    recent_since: str,
) -> None:
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    summary.update(
        {
            "source": "zhaopin",
            "keyword": "AI/ML related",
            "deduped": len({str(row.get("job_id")) for row in all_rows}),
            "saved": len(all_rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page_cache",
        "topic": "AI/ML related jobs",
        "keywords": helper.KEYWORDS,
        "cities": list(helper.CITIES.values()),
        "recent_since": recent_since,
        "existing_before": existing_count,
        "added": len(added),
        "total_after": len(all_rows),
        "scrape_time": scrape_time,
        "stats": stats,
        "task_samples": task_samples,
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
