#!/usr/bin/env python3
"""Rebuild JD data with title-only strong AI keyword filtering."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib.util
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
REBUILD_PATH = REPO_ROOT / "scripts" / "rebuild_strong_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"


TITLE_CJK_TERMS = [
    "\u4eba\u5de5\u667a\u80fd",  # artificial intelligence
    "\u673a\u5668\u5b66\u4e60",  # machine learning
    "\u7b97\u6cd5",  # algorithm
    "\u5927\u6a21\u578b",  # large model
    "\u6df1\u5ea6\u5b66\u4e60",  # deep learning
    "\u8ba1\u7b97\u673a\u89c6\u89c9",  # computer vision
    "\u81ea\u7136\u8bed\u8a00\u5904\u7406",  # NLP
    "\u5927\u8bed\u8a00\u6a21\u578b",  # LLM
]
TITLE_ASCII_TOKEN_TERMS = ["AI", "NLP", "CV", "LLM"]
TITLE_ASCII_PHRASES = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "computer vision",
    "large language model",
    "large language models",
    "algorithm",
    "algorithms",
]
STRONG_SYNONYM_CJK_TERMS = [
    "\u5927\u8bed\u8a00\u6a21\u578b",
    "\u591a\u6a21\u6001",
    "\u667a\u80fd\u4f53",
    "\u751f\u6210\u5f0f",
    "\u77e5\u8bc6\u56fe\u8c31",
    "\u5f3a\u5316\u5b66\u4e60",
    "\u673a\u5668\u89c6\u89c9",
    "\u89c6\u89c9\u611f\u77e5",
    "\u89c6\u89c9",
    "\u56fe\u50cf\u5904\u7406",
    "\u56fe\u50cf\u8bc6\u522b",
    "\u56fe\u50cf",
    "\u76ee\u6807\u68c0\u6d4b",
    "\u8bed\u97f3\u8bc6\u522b",
    "\u8bed\u97f3\u7b97\u6cd5",
    "\u8bed\u97f3\u5408\u6210",
    "\u8bed\u97f3\u5927\u6a21\u578b",
    "\u63a8\u8350\u7cfb\u7edf",
    "\u641c\u7d22\u63a8\u8350",
    "\u63a8\u8350\u5f15\u64ce",
    "\u6570\u636e\u6316\u6398",
    "\u6a21\u578b\u8bad\u7ec3",
    "\u6a21\u578b\u63a8\u7406",
    "\u6a21\u578b\u5fae\u8c03",
    "\u6a21\u578b\u90e8\u7f72",
    "\u63d0\u793a\u8bcd",
    "\u4eba\u8138\u8bc6\u522b",
    "\u5177\u8eab\u667a\u80fd",
]
STRONG_SYNONYM_ASCII_TOKEN_TERMS = [
    "RAG",
    "AGENT",
    "TRANSFORMER",
    "PYTORCH",
    "TENSORFLOW",
    "MLOPS",
    "OCR",
    "PROMPT",
    "AIOPS",
    "AIOT",
    "AI4S",
    "AIDD",
    "ASR",
    "TTS",
]
STRONG_SYNONYM_ASCII_PHRASES = [
    "data scientist",
    "data science",
    "machine vision",
    "image processing",
    "speech recognition",
    "knowledge graph",
    "recommendation system",
    "recommender system",
    "reinforcement learning",
    "model training",
    "model inference",
    "model fine tuning",
    "prompt engineer",
]

FETCH_KEYWORDS = [
    "AI算法",
    "算法工程师",
    "算法开发",
    "算法研发",
    "算法专家",
    "机器学习工程师",
    "机器学习算法",
    "深度学习工程师",
    "深度学习算法",
    "大模型算法工程师",
    "大模型工程师",
    "大模型研发工程师",
    "大模型开发工程师",
    "LLM算法",
    "LLM工程师",
    "NLP算法工程师",
    "NLP工程师",
    "自然语言处理工程师",
    "计算机视觉工程师",
    "计算机视觉算法",
    "CV算法",
    "图像算法工程师",
    "视觉算法工程师",
    "推荐算法工程师",
    "搜索算法工程师",
    "人工智能工程师",
    "AI研发工程师",
    "AI开发工程师",
    "AI架构师",
    "智能体开发",
    "Agent开发工程师",
    "RAG开发工程师",
    "知识图谱工程师",
    "机器视觉工程师",
    "目标检测",
    "多模态大模型",
    "强化学习工程师",
    "语音算法",
    "语音识别工程师",
    "数据挖掘工程师",
]
FETCH_CITY_CODES = [
    "all",
    "530",
    "538",
    "765",
    "763",
    "653",
    "801",
    "736",
    "854",
    "702",
    "551",
    "664",
    "600",
]

FETCH_KEYWORDS = [
    "AI\u7b97\u6cd5",
    "AI\u5de5\u7a0b\u5e08",
    "AI\u7814\u53d1\u5de5\u7a0b\u5e08",
    "AI\u5f00\u53d1\u5de5\u7a0b\u5e08",
    "AI\u67b6\u6784\u5e08",
    "\u4eba\u5de5\u667a\u80fd\u5de5\u7a0b\u5e08",
    "\u4eba\u5de5\u667a\u80fd\u7b97\u6cd5",
    "\u673a\u5668\u5b66\u4e60\u5de5\u7a0b\u5e08",
    "\u673a\u5668\u5b66\u4e60\u7b97\u6cd5",
    "\u6df1\u5ea6\u5b66\u4e60\u5de5\u7a0b\u5e08",
    "\u6df1\u5ea6\u5b66\u4e60\u7b97\u6cd5",
    "\u7b97\u6cd5\u5de5\u7a0b\u5e08",
    "\u7b97\u6cd5\u7814\u53d1",
    "\u7b97\u6cd5\u5f00\u53d1",
    "\u7b97\u6cd5\u4e13\u5bb6",
    "\u7b97\u6cd5\u7814\u7a76\u5458",
    "\u5927\u6a21\u578b\u5de5\u7a0b\u5e08",
    "\u5927\u6a21\u578b\u7b97\u6cd5",
    "\u5927\u6a21\u578b\u7814\u53d1",
    "\u5927\u6a21\u578b\u5f00\u53d1",
    "LLM\u5de5\u7a0b\u5e08",
    "LLM\u7b97\u6cd5",
    "LLM\u7814\u53d1",
    "NLP\u5de5\u7a0b\u5e08",
    "NLP\u7b97\u6cd5",
    "NLP\u7814\u53d1",
    "\u81ea\u7136\u8bed\u8a00\u5904\u7406\u5de5\u7a0b\u5e08",
    "\u81ea\u7136\u8bed\u8a00\u5904\u7406\u7b97\u6cd5",
    "CV\u7b97\u6cd5",
    "CV\u5de5\u7a0b\u5e08",
    "\u8ba1\u7b97\u673a\u89c6\u89c9\u5de5\u7a0b\u5e08",
    "\u8ba1\u7b97\u673a\u89c6\u89c9\u7b97\u6cd5",
    "\u89c6\u89c9\u7b97\u6cd5\u5de5\u7a0b\u5e08",
    "\u56fe\u50cf\u7b97\u6cd5\u5de5\u7a0b\u5e08",
    "\u63a8\u8350\u7b97\u6cd5\u5de5\u7a0b\u5e08",
    "\u641c\u7d22\u7b97\u6cd5\u5de5\u7a0b\u5e08",
]

WEAK_CJK_TERMS = [
    "\u9500\u552e",
    "\u552e\u524d",
    "\u552e\u540e",
    "\u8bfe\u7a0b\u987e\u95ee",
    "\u987e\u95ee",
    "\u54a8\u8be2",
    "\u8bb2\u5e08",
    "\u6559\u5e08",
    "\u8001\u5e08",
    "\u52a9\u6559",
    "\u7f16\u5bfc",
    "\u5bfc\u6f14",
    "\u8bbe\u8ba1\u5e08",
    "\u7f8e\u5de5",
    "\u8fd0\u8425",
    "\u5185\u5bb9\u5236\u4f5c",
    "\u5185\u5bb9\u8fd0\u8425",
    "\u5185\u5bb9\u5ba1\u6838",
    "\u4e3b\u64ad",
    "\u6587\u6848",
    "\u526a\u8f91",
    "\u5e02\u573a",
    "\u5546\u52a1",
    "\u5ba2\u670d",
    "\u62db\u751f",
    "\u884c\u653f",
    "\u8d22\u52a1",
    "\u4f1a\u8ba1",
    "\u4eba\u4e8b",
    "\u62db\u8058",
    "\u6559\u7814",
    "\u6559\u57f9",
    "\u65b0\u5a92\u4f53",
    "\u77ed\u89c6\u9891",
    "\u6296\u97f3",
    "\u5feb\u624b",
    "\u8bed\u97f3\u5385",
    "\u8bed\u97f3\u804a\u5929",
    "\u804a\u5929\u5ba4",
    "\u804a\u5929\u5458",
    "\u966a\u804a",
    "\u65e5\u7ed3",
    "\u5468\u7ed3",
    "\u96f6\u82b1\u94b1",
    "\u517c\u804c",
    "\u526f\u4e1a",
    "\u5c45\u5bb6",
    "\u5c0f\u767d",
    "\u4e0d\u9732\u8138",
    "\u5f00\u64ad",
    "\u76f4\u64ad",
    "\u5531\u6b4c",
    "\u72fc\u4eba\u6740",
    "\u5f39\u5e55",
    "\u503e\u542c\u5458",
    "\u4e3b\u6301",
    "\u4e34\u5e8a\u7814\u7a76",
    "\u76d1\u67e5\u5458",
    "\u6807\u6ce8",
    "\u8bad\u7ec3\u5e08",
    "\u8d28\u68c0",
    "\u8d28\u63a7",
    "\u5ba1\u6838",
    "\u52a8\u753b\u5e08",
    "\u52a8\u753b",
    "\u5f71\u89c6",
    "\u7f8e\u5b66",
    "\u4fee\u56fe",
    "\u6d77\u62a5",
    "\u5e73\u9762\u8bbe\u8ba1",
    "UI\u8bbe\u8ba1",
    "\u4ea7\u54c1\u7ecf\u7406",
    "\u9879\u76ee\u7ecf\u7406",
    "\u89e3\u51b3\u65b9\u6848",
    "\u5b9e\u65bd",
    "\u4ea4\u4ed8",
    "\u6280\u672f\u652f\u6301",
    "\u552e\u524d\u5de5\u7a0b\u5e08",
    "\u5ba2\u6237\u6210\u529f",
    "\u4ea7\u54c1\u8fd0\u8425",
    "\u9879\u76ee\u7ba1\u7406",
    "\u670d\u52a1\u5668",
    "\u673a\u67dc",
    "\u673a\u6784\u8bbe\u8ba1",
    "\u7ed3\u6784\u8bbe\u8ba1",
    "CDU",
    "AIDC",
    "\u7ba1\u57f9",
    "\u57ce\u5e02\u7ecf\u7406",
    "\u533a\u57df\u7ecf\u7406",
    "\u533a\u57df\u4e3b\u7ba1",
    "\u533a\u57df\u4e1a\u52a1",
    "\u4e1a\u52a1\u7ecf\u7406",
    "\u4e1a\u52a1\u4e3b\u7ba1",
    "\u5ba2\u6237\u7ecf\u7406",
    "\u6e20\u9053\u7ecf\u7406",
    "\u63a8\u5e7f",
    "\u4ee3\u8868",
    "\u529e\u4e8b\u5904",
    "\u7701\u533a",
    "\u5730\u533a\u7ecf\u7406",
    "\u53bf\u529e",
]
WEAK_ASCII_TOKEN_TERMS = [
    "HR",
    "SALES",
    "MARKETING",
    "CUSTOMER",
    "SUPPORT",
    "TEACHER",
    "LECTURER",
    "DESIGNER",
    "COPYWRITER",
    "OPERATION",
    "OPERATIONS",
    "EDITOR",
    "DIRECTOR",
    "CONSULTANT",
    "COUNSELOR",
    "ADVISOR",
    "RECRUITER",
]

TECH_TITLE_TERMS = [
    "\u5de5\u7a0b\u5e08",
    "\u5f00\u53d1",
    "\u7814\u53d1",
    "\u7b97\u6cd5",
    "\u67b6\u6784",
    "\u67b6\u6784\u5e08",
    "\u79d1\u5b66\u5bb6",
    "\u7814\u7a76\u5458",
    "\u6280\u672f",
    "\u5efa\u6a21",
    "\u6a21\u578b",
    "\u63a8\u7406",
    "\u8bad\u7ec3",
    "\u5fae\u8c03",
    "\u90e8\u7f72",
    "\u8bc6\u522b",
    "\u68c0\u6d4b",
    "\u63a8\u8350",
    "\u641c\u7d22",
    "\u89c6\u89c9",
    "\u8bed\u8a00\u5904\u7406",
    "\u4e13\u5bb6",
    "NLP",
    "CV",
    "LLM",
]


TITLE_TOKEN_RE = re.compile(
    "|".join(
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])" for term in TITLE_ASCII_TOKEN_TERMS
    ),
    re.IGNORECASE,
)
WEAK_TOKEN_RE = re.compile(
    "|".join(
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])" for term in WEAK_ASCII_TOKEN_TERMS
    ),
    re.IGNORECASE,
)
STRONG_SYNONYM_TOKEN_RE = re.compile(
    "|".join(
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])" for term in STRONG_SYNONYM_ASCII_TOKEN_TERMS
    ),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CacheTask:
    keyword: str
    city_code: str
    page: int

    @property
    def url(self) -> str:
        keyword = quote(self.keyword)
        if self.city_code == "all":
            return f"https://sou.zhaopin.com/?kw={keyword}&kt=3&p={self.page}"
        return f"https://sou.zhaopin.com/?jl={self.city_code}&kw={keyword}&kt=3&p={self.page}"

    @property
    def cache_path(self) -> Path:
        safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", self.keyword)
        return FETCH_ROOT / f"{self.city_code}_{safe_keyword}_{self.page:03d}.html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=15000)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--max-cache-page", type=int, default=30)
    parser.add_argument("--min-cache-bytes", type=int, default=50000)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--dedupe-signature", action="store_true")
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--fetch-start-page", type=int, default=6)
    parser.add_argument("--fetch-max-page", type=int, default=12)
    parser.add_argument("--fetch-workers", type=int, default=6)
    parser.add_argument("--write-partial", action="store_true")
    args = parser.parse_args()

    helper = load_module(HELPER_PATH, "append_ai_jd_data_title_refill")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_title_refill")
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    stats: dict[str, int] = {
        "existing_before": 0,
        "existing_kept": 0,
        "existing_kept_strict_title": 0,
        "existing_kept_strong_synonym_title": 0,
        "existing_kept_text_strict_title": 0,
        "existing_kept_text_strong_synonym_title": 0,
        "existing_removed_non_zhaopin": 0,
        "existing_removed_duplicate_id": 0,
        "existing_removed_duplicate_signature": 0,
        "existing_removed_no_title_keyword": 0,
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
        "cache_weak_title_skipped": 0,
        "cache_old_skipped": 0,
        "cache_empty_jd_text_skipped": 0,
        "fetch_tasks_attempted": 0,
        "fetch_pages_parsed": 0,
        "fetch_positions_seen": 0,
        "added_from_fetch": 0,
    }
    stats["dedupe_signature_enabled"] = int(args.dedupe_signature)

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()

    existing_rows = read_jsonl(JD_JSONL)
    stats["existing_before"] = len(existing_rows)
    for row in existing_rows:
        reason = rejection_reason(row, cutoff)
        if row.get("source_name") != "zhaopin":
            stats["existing_removed_non_zhaopin"] += 1
            continue
        job_id = row.get("job_id")
        key = str(job_id) if job_id is not None else ""
        if not key or key in seen_ids:
            stats["existing_removed_duplicate_id"] += 1
            continue
        signature = row_signature(row)
        if args.dedupe_signature and signature in seen_signatures:
            stats["existing_removed_duplicate_signature"] += 1
            continue
        if reason:
            stats[f"existing_removed_{reason}"] += 1
            continue
        rows.append(row)
        seen_ids.add(key)
        seen_signatures.add(signature)
        stats["existing_kept"] += 1
        stats[f"existing_kept_{row_match_tier(row)}_title"] += 1

    start = time.time()
    cache_files = list_cache_files(args.max_cache_page, args.min_cache_bytes)
    batch_size = max(1, args.workers) * 8
    for index in range(0, len(cache_files), batch_size):
        if len(rows) >= args.target_total:
            break
        batch = cache_files[index : index + batch_size]
        stats["cache_files_scanned"] += len(batch)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(read_cache_file, helper, path) for path in batch]
            for future in concurrent.futures.as_completed(futures):
                if len(rows) >= args.target_total:
                    break
                task, items = future.result()
                if task is None or not items:
                    continue
                stats["cache_pages_parsed"] += 1
                stats["positions_seen"] += len(items)
                accept_items(
                    helper=helper,
                    task=task,
                    items=items,
                    rows=rows,
                    seen_ids=seen_ids,
                    seen_signatures=seen_signatures,
                    stats=stats,
                    cutoff=cutoff,
                    scrape_time=scrape_time,
                    target_total=args.target_total,
                    dedupe_signature=args.dedupe_signature,
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
                            "added_from_cache": stats["added_from_cache"],
                            "elapsed_seconds": round(time.time() - start, 1),
                        }
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    if len(rows) < args.target_total and args.fetch_missing:
        fetch_start = time.time()
        fetch_tasks = list_fetch_tasks(args.fetch_start_page, args.fetch_max_page, args.min_cache_bytes)
        fetch_batch_size = max(1, args.fetch_workers) * 4
        for index in range(0, len(fetch_tasks), fetch_batch_size):
            if len(rows) >= args.target_total:
                break
            batch = fetch_tasks[index : index + fetch_batch_size]
            stats["fetch_tasks_attempted"] += len(batch)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.fetch_workers)) as executor:
                futures = [executor.submit(fetch_cache_file, rebuild, helper, task) for task in batch]
                for future in concurrent.futures.as_completed(futures):
                    if len(rows) >= args.target_total:
                        break
                    task, items = future.result()
                    if task is None or not items:
                        continue
                    stats["fetch_pages_parsed"] += 1
                    stats["fetch_positions_seen"] += len(items)
                    before = stats["added_from_cache"]
                    accept_items(
                        helper=helper,
                        task=task,
                        items=items,
                        rows=rows,
                        seen_ids=seen_ids,
                        seen_signatures=seen_signatures,
                        stats=stats,
                        cutoff=cutoff,
                        scrape_time=scrape_time,
                        target_total=args.target_total,
                        dedupe_signature=args.dedupe_signature,
                    )
                    stats["added_from_fetch"] += stats["added_from_cache"] - before
            if stats["fetch_tasks_attempted"] % 240 == 0 or len(rows) >= args.target_total:
                print(
                    json.dumps(
                        {
                            "fetch_progress": {
                                "rows": len(rows),
                                "target_total": args.target_total,
                                "fetch_tasks_attempted": stats["fetch_tasks_attempted"],
                                "fetch_pages_parsed": stats["fetch_pages_parsed"],
                                "fetch_positions_seen": stats["fetch_positions_seen"],
                                "added_from_fetch": stats["added_from_fetch"],
                                "elapsed_seconds": round(time.time() - fetch_start, 1),
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
                "unique_signatures": len({row_signature(row) for row in rows}),
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
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def list_cache_files(max_page: int, min_cache_bytes: int) -> list[Path]:
    files: list[tuple[int, int, int, str, str, Path]] = []
    for path in FETCH_ROOT.glob("*.html"):
        if path.stat().st_size < min_cache_bytes:
            continue
        match = re.match(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
        if not match:
            continue
        page = int(match.group("page"))
        if 1 <= page <= max_page:
            keyword = match.group("keyword").replace("_", " ")
            priority, rank = cache_keyword_priority(keyword)
            files.append((priority, rank, -page, keyword.casefold(), match.group("city"), path))
    return [item[5] for item in sorted(files)]


def cache_keyword_priority(keyword: str) -> tuple[int, int]:
    high_yield_terms = [
        "\u7b97\u6cd5",
        "\u5927\u6a21\u578b",
        "\u673a\u5668\u5b66\u4e60",
        "\u6df1\u5ea6\u5b66\u4e60",
        "\u4eba\u5de5\u667a\u80fd",
        "\u5927\u8bed\u8a00\u6a21\u578b",
        "\u8ba1\u7b97\u673a\u89c6\u89c9",
        "\u81ea\u7136\u8bed\u8a00\u5904\u7406",
        "LLM",
        "NLP",
        "CV",
        "AI",
        "AIGC",
        "ML",
        "\u667a\u80fd\u4f53",
        "\u591a\u6a21\u6001",
        "\u89c6\u89c9",
        "\u56fe\u50cf",
        "\u63a8\u8350\u7cfb\u7edf",
        "\u641c\u7d22\u63a8\u8350",
        "\u6570\u636e\u6316\u6398",
        "\u6a21\u578b\u8bad\u7ec3",
        "\u6a21\u578b\u63a8\u7406",
        "RAG",
        "Agent",
        "Transformer",
        "PyTorch",
        "TensorFlow",
    ]
    for index, term in enumerate(high_yield_terms):
        if term in keyword:
            return 0, index
    if has_any_title_keyword(keyword):
        return 1, len(high_yield_terms)
    return 2, len(high_yield_terms) + 1


def task_from_cache_path(path: Path) -> CacheTask | None:
    match = re.match(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
    if not match:
        return None
    return CacheTask(
        keyword=match.group("keyword").replace("_", " "),
        city_code=match.group("city"),
        page=int(match.group("page")),
    )


def read_cache_file(helper: Any, path: Path) -> tuple[CacheTask | None, list[dict[str, Any]]]:
    task = task_from_cache_path(path)
    if task is None:
        return None, []
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return task, []
    return task, helper.parse_positions(html)


def list_fetch_tasks(start_page: int, max_page: int, min_cache_bytes: int) -> list[CacheTask]:
    tasks: list[CacheTask] = []
    for page in range(max(1, start_page), max_page + 1):
        for keyword in FETCH_KEYWORDS:
            for city_code in FETCH_CITY_CODES:
                task = CacheTask(keyword=keyword, city_code=city_code, page=page)
                if task.cache_path.exists() and task.cache_path.stat().st_size >= min_cache_bytes:
                    continue
                tasks.append(task)
    return tasks


def fetch_cache_file(rebuild: Any, helper: Any, task: CacheTask) -> tuple[CacheTask | None, list[dict[str, Any]]]:
    html = fetch_zhaopin_html_with_timeout(task)
    if not html:
        return task, []
    return task, helper.parse_positions(html)


def fetch_zhaopin_html_with_timeout(task: CacheTask) -> str:
    if task.cache_path.exists():
        cached = task.cache_path.read_text(encoding="utf-8", errors="replace")
        if '"positionList"' in cached or "__INITIAL_STATE__" in cached:
            return cached
    task.cache_path.parent.mkdir(parents=True, exist_ok=True)
    ps_command = (
        "$ProgressPreference='SilentlyContinue'; "
        f"$uri='{task.url}'; "
        "$headers=@{"
        "'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36';"
        "'Accept-Language'='zh-CN,zh;q=0.9';"
        "'Referer'='https://sou.zhaopin.com/'"
        "}; "
        "(Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $headers -TimeoutSec 30).Content"
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    html = completed.stdout
    if '"positionList"' not in html and "__INITIAL_STATE__" not in html:
        return ""
    task.cache_path.write_text(html, encoding="utf-8")
    return html


def accept_items(
    *,
    helper: Any,
    task: CacheTask,
    items: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    seen_ids: set[str],
    seen_signatures: set[str],
    stats: dict[str, int],
    cutoff: datetime,
    scrape_time: str,
    target_total: int,
    dedupe_signature: bool,
) -> None:
    for item in items:
        if len(rows) >= target_total:
            break
        if not isinstance(item, dict):
            continue
        job_id = item.get("jobId")
        if job_id is None:
            stats["cache_missing_id_skipped"] += 1
            continue
        key = str(job_id)
        if key in seen_ids:
            stats["cache_duplicate_id_skipped"] += 1
            continue
        row = helper.convert_item(item, task, scrape_time)
        reason = rejection_reason(row, cutoff)
        if reason:
            stats[f"cache_{reason}_skipped"] += 1
            continue
        signature = row_signature(row)
        if dedupe_signature and signature in seen_signatures:
            stats["cache_duplicate_signature_skipped"] += 1
            continue
        rows.append(row)
        seen_ids.add(key)
        seen_signatures.add(signature)
        stats["added_from_cache"] += 1
        stats[f"cache_added_{row_match_tier(row)}_title"] += 1


def rejection_reason(row: dict[str, Any], cutoff: datetime) -> str:
    title = str(row.get("job_title") or "")
    if is_weak_title(title):
        return "weak_title"
    if not row_match_tier(row):
        return "no_title_keyword"
    publish_date = str(row.get("publish_date") or "")
    if not is_recent_date(publish_date, cutoff):
        return "old"
    if not str(row.get("jd_text") or "").strip():
        return "empty_jd_text"
    return ""


def has_title_keyword(title: str) -> bool:
    if any(term in title for term in TITLE_CJK_TERMS):
        return True
    folded = title.casefold()
    if any(phrase in folded for phrase in TITLE_ASCII_PHRASES):
        return True
    return bool(TITLE_TOKEN_RE.search(title))


def has_any_title_keyword(title: str) -> bool:
    return bool(title_match_tier(title))


def has_strong_synonym_title_keyword(title: str) -> bool:
    if any(term in title for term in STRONG_SYNONYM_CJK_TERMS):
        return True
    folded = title.casefold()
    if any(phrase in folded for phrase in STRONG_SYNONYM_ASCII_PHRASES):
        return True
    return bool(STRONG_SYNONYM_TOKEN_RE.search(title))


def title_match_tier(title: str) -> str:
    if has_title_keyword(title):
        return "strict"
    return ""


def row_match_tier(row: dict[str, Any]) -> str:
    title_tier = title_match_tier(str(row.get("job_title") or ""))
    if title_tier:
        return title_tier
    if has_title_keyword(row_text_for_match(row)):
        return "text_strict"
    return ""


def row_text_for_match(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("job_title") or ""),
        str(row.get("industry") or ""),
        str(row.get("jd_text") or ""),
    ]
    for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
        value = row.get(key) or []
        pieces.append(" ".join(map(str, value)) if isinstance(value, list) else str(value))
    return " ".join(pieces)


def is_weak_title(title: str) -> bool:
    if any(term in title for term in WEAK_CJK_TERMS):
        return True
    if WEAK_TOKEN_RE.search(title):
        return True
    return not is_technical_title(title)


def is_technical_title(title: str) -> bool:
    return any(term in title for term in TECH_TITLE_TERMS)


def is_recent_date(value: str, cutoff: datetime) -> bool:
    parsed = parse_publish_time(value)
    return parsed is not None and parsed >= cutoff


def parse_publish_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt, width in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:width], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def row_signature(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("job_title") or ""),
        str(row.get("company_name") or ""),
        str(row.get("location") or ""),
    ]
    normalized = [re.sub(r"\s+", "", piece).casefold() for piece in pieces]
    return "|".join(normalized)


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
            "keyword": "domestic title-keyword strong AI/ML jobs only",
            "deduped": len({str(row.get("job_id")) for row in rows}),
            "saved": len(rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
            "source_counts": source_counts,
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page_cache_title_refill",
        "topic": "domestic jobs whose title or JD text contains strong AI keywords and whose title excludes weak-related roles",
        "site": "https://sou.zhaopin.com/",
        "recent_since": recent_since,
        "target_total": target_total,
        "total_after": len(rows),
        "max_cache_page": max_cache_page,
        "dedupe": ["job_id"] + (["job_title+company_name+location"] if stats.get("dedupe_signature_enabled") else []),
        "filter": {
            "title_required_terms": TITLE_CJK_TERMS + TITLE_ASCII_TOKEN_TERMS + TITLE_ASCII_PHRASES,
            "strong_synonym_title_terms": (
                STRONG_SYNONYM_CJK_TERMS + STRONG_SYNONYM_ASCII_TOKEN_TERMS + STRONG_SYNONYM_ASCII_PHRASES
            ),
            "weak_title_terms": WEAK_CJK_TERMS + WEAK_ASCII_TOKEN_TERMS,
            "match_scope": "job_title first, then jd_text/responsibilities/requirements/skills",
            "domestic_only": True,
            "source_name": "zhaopin",
            "jd_text_required": True,
        },
        "stats": stats,
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
