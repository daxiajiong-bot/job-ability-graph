#!/usr/bin/env python3
"""Append AI/ML related Zhaopin JD records to data/small-raw/jd_raw.jsonl."""

from __future__ import annotations

import argparse
import csv
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
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"

CSV_FIELDS = [
    "source_type",
    "source_name",
    "page",
    "job_id",
    "job_title",
    "company_name",
    "industry",
    "location",
    "salary_min",
    "salary_max",
    "experience",
    "education",
    "publish_date",
    "jd_text",
    "responsibilities",
    "requirements",
    "skills_raw",
    "skills_norm",
    "url",
    "scrape_time",
]

KEYWORDS = [
    "人工智能",
    "机器学习",
    "深度学习",
    "大模型",
    "算法工程师",
    "AI算法",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "推荐算法",
    "数据挖掘",
    "AIGC",
    "多模态",
    "LLM",
    "PyTorch",
    "TensorFlow",
    "模型训练",
]

CITIES = {
    "530": "北京",
    "538": "上海",
    "763": "广州",
    "765": "深圳",
    "653": "杭州",
    "801": "成都",
    "736": "南京",
    "854": "武汉",
    "702": "西安",
    "551": "天津",
    "664": "苏州",
    "600": "重庆",
}

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
INITIAL_STATE_RE = re.compile(r"__INITIAL_STATE__=(\{.*?\})</script><script", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class FetchTask:
    keyword: str
    city_code: str
    city_name: str
    page: int

    @property
    def url(self) -> str:
        keyword = quote(self.keyword)
        return f"https://sou.zhaopin.com/?jl={self.city_code}&kw={keyword}&kt=3&p={self.page}"

    @property
    def cache_path(self) -> Path:
        safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", self.keyword)
        return FETCH_ROOT / f"{self.city_code}_{safe_keyword}_{self.page:03d}.html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=3000)
    parser.add_argument("--max-pages-per-query-city", type=int, default=20)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--sleep-seconds", type=float, default=0.12)
    parser.add_argument("--cache-only", action="store_true", help="Only parse cached HTML files; do not fetch network.")
    args = parser.parse_args()

    existing_rows = read_jsonl(JD_JSONL)
    existing_ids = {str(row.get("job_id")) for row in existing_rows if row.get("job_id") is not None}
    target_add = max(0, args.target_total - len(existing_rows))
    if target_add == 0:
        print(json.dumps({"status": "already_complete", "total": len(existing_rows)}, ensure_ascii=False, indent=2))
        return 0

    FETCH_ROOT.mkdir(parents=True, exist_ok=True)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    cutoff = parse_date(args.recent_since)
    added: list[dict[str, Any]] = []
    seen = set(existing_ids)
    stats = {
        "pages_attempted": 0,
        "pages_parsed": 0,
        "pages_failed": 0,
        "positions_seen": 0,
        "duplicate_skipped": 0,
        "old_skipped": 0,
        "irrelevant_skipped": 0,
        "missing_id_skipped": 0,
    }
    used_tasks: list[dict[str, Any]] = []

    task_iterable = iter_cached_tasks() if args.cache_only else iter_tasks(args.max_pages_per_query_city)
    for task in task_iterable:
        if len(added) >= target_add:
            break
        stats["pages_attempted"] += 1
        html = fetch_html(task, cache_only=args.cache_only)
        if not html:
            stats["pages_failed"] += 1
            continue
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)
        items = parse_positions(html)
        if not items:
            continue
        stats["pages_parsed"] += 1
        stats["positions_seen"] += len(items)
        used_tasks.append({"keyword": task.keyword, "city": task.city_name, "city_code": task.city_code, "page": task.page})
        for item in items:
            if len(added) >= target_add:
                break
            job_id = item.get("jobId")
            if job_id is None:
                stats["missing_id_skipped"] += 1
                continue
            key = str(job_id)
            if key in seen:
                stats["duplicate_skipped"] += 1
                continue
            row = convert_item(item, task, scrape_time)
            if not is_recent(row["publish_date"], cutoff):
                stats["old_skipped"] += 1
                continue
            if not is_ai_related(row, task.keyword):
                stats["irrelevant_skipped"] += 1
                continue
            seen.add(key)
            added.append(row)
        if stats["pages_attempted"] % 50 == 0 or len(added) >= target_add:
            print(
                json.dumps(
                    {
                        "progress": {
                            "pages_attempted": stats["pages_attempted"],
                            "pages_parsed": stats["pages_parsed"],
                            "pages_failed": stats["pages_failed"],
                            "added": len(added),
                            "target_add": target_add,
                        }
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    if len(added) < target_add:
        raise SystemExit(
            f"Only collected {len(added)} new rows, need {target_add}. "
            f"Stats: {json.dumps(stats, ensure_ascii=False)}"
        )

    all_rows = [*existing_rows, *added]
    write_jsonl(JD_JSONL, all_rows)
    write_csv(JD_CSV, all_rows)
    update_summary(
        existing_count=len(existing_rows),
        added=added,
        all_rows=all_rows,
        stats=stats,
        used_tasks=used_tasks,
        scrape_time=scrape_time,
        recent_since=args.recent_since,
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
        )
    )
    return 0


def iter_tasks(max_pages: int) -> list[FetchTask]:
    tasks: list[FetchTask] = []
    for page in range(1, max_pages + 1):
        for keyword in KEYWORDS:
            for city_code, city_name in CITIES.items():
                tasks.append(FetchTask(keyword=keyword, city_code=city_code, city_name=city_name, page=page))
    return tasks


def iter_cached_tasks() -> list[FetchTask]:
    tasks: list[FetchTask] = []
    city_lookup = CITIES
    for path in sorted(FETCH_ROOT.glob("*.html"), key=lambda item: item.name):
        match = re.match(r"(?P<city>\d+)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
        if not match:
            continue
        city_code = match.group("city")
        keyword = match.group("keyword")
        page = int(match.group("page"))
        tasks.append(FetchTask(keyword=keyword, city_code=city_code, city_name=city_lookup.get(city_code, city_code), page=page))
    return tasks


def fetch_html(task: FetchTask, *, cache_only: bool = False) -> str:
    if task.cache_path.exists():
        return task.cache_path.read_text(encoding="utf-8", errors="replace")
    if cache_only:
        return ""
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
        )
    except subprocess.CalledProcessError as exc:
        print(
            json.dumps(
                {
                    "fetch_failed": {
                        "keyword": task.keyword,
                        "city": task.city_name,
                        "page": task.page,
                        "returncode": exc.returncode,
                        "stderr": (exc.stderr or "")[-300:],
                    }
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
            flush=True,
        )
        return ""
    html = completed.stdout
    task.cache_path.write_text(html, encoding="utf-8")
    return html


def parse_positions(html: str) -> list[dict[str, Any]]:
    items = decode_json_array_after_key(html, '"positionList"')
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]

    match = INITIAL_STATE_RE.search(html)
    if not match:
        return []
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    items = state.get("positionList")
    return items if isinstance(items, list) else []


def decode_json_array_after_key(text: str, key: str) -> Any:
    key_index = text.find(key)
    if key_index < 0:
        return None
    start = text.find("[", key_index)
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value


def extract_json_array_after_key(text: str, key: str) -> str:
    key_index = text.find(key)
    if key_index < 0:
        return ""
    start = text.find("[", key_index)
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def convert_item(item: dict[str, Any], task: FetchTask, scrape_time: str) -> dict[str, Any]:
    jd_text = description_for(item)
    lines = split_lines(jd_text)
    skills = skill_names(item)
    salary_min, salary_max = parse_salary(item)
    return {
        "source_type": "job_platform",
        "source_name": "zhaopin",
        "page": task.page,
        "job_id": item.get("jobId"),
        "job_title": first(item.get("name"), get_path(item, ["jobDetailData", "position", "base", "positionName"])),
        "company_name": first(item.get("companyName"), get_path(item, ["jobDetailData", "companyProxy", "companyName"])),
        "industry": first(item.get("industryName")),
        "location": location_for(item),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "experience": first(item.get("workingExp"), get_path(item, ["jobDetailData", "position", "base", "positionWorkingExp"])),
        "education": first(item.get("education"), get_path(item, ["jobDetailData", "position", "base", "education"])),
        "publish_date": first(item.get("publishTime"), get_path(item, ["jobDetailData", "position", "date", "positionPublishTime"])),
        "jd_text": jd_text,
        "responsibilities": lines,
        "requirements": lines,
        "skills_raw": skills,
        "skills_norm": skills,
        "url": first(item.get("positionUrl"), item.get("positionURL"), get_path(item, ["jobDetailData", "position", "base", "positionUrl"])),
        "scrape_time": scrape_time,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in CSV_FIELDS}
            for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
                output[key] = json.dumps(output[key] if isinstance(output[key], list) else [], ensure_ascii=False)
            writer.writerow(output)


def update_summary(
    *,
    existing_count: int,
    added: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    stats: dict[str, int],
    used_tasks: list[dict[str, Any]],
    scrape_time: str,
    recent_since: str,
) -> None:
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    summary.update(
        {
            "source": "zhaopin",
            "keyword": "AI/ML related",
            "fetched": stats["positions_seen"],
            "deduped": len({str(row.get("job_id")) for row in all_rows}),
            "saved": len(all_rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page",
        "topic": "AI/ML related jobs",
        "keywords": KEYWORDS,
        "cities": list(CITIES.values()),
        "recent_since": recent_since,
        "existing_before": existing_count,
        "added": len(added),
        "total_after": len(all_rows),
        "scrape_time": scrape_time,
        "stats": stats,
        "used_task_count": len(used_tasks),
        "first_tasks": used_tasks[:20],
        "last_tasks": used_tasks[-20:],
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_ai_related(row: dict[str, Any], keyword: str) -> bool:
    text = " ".join(
        [
            str(keyword),
            str(row.get("job_title") or ""),
            str(row.get("industry") or ""),
            str(row.get("jd_text") or ""),
            " ".join(row.get("skills_raw") or []),
            " ".join(row.get("skills_norm") or []),
        ]
    )
    return bool(AI_RE.search(text))


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def is_recent(value: str, cutoff: datetime) -> bool:
    parsed = parse_publish_time(value)
    return parsed is not None and parsed >= cutoff


def parse_publish_time(value: str) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    for fmt, width in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:width], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def description_for(item: dict[str, Any]) -> str:
    description = first(
        get_path(item, ["jobDetailData", "position", "desc", "description"]),
        item.get("jobSummary"),
        item.get("positionHighlight"),
    )
    description = normalize_text(description)
    if description:
        return description
    pieces = [
        f"岗位名称：{clean(item.get('name'))}",
        f"公司名称：{clean(item.get('companyName'))}",
        f"技能标签：{'、'.join(skill_names(item))}",
    ]
    return "\n".join(piece for piece in pieces if piece.split("：", 1)[-1])


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"\r?\n+", normalize_text(text)) if line.strip()]


def normalize_text(value: Any) -> str:
    text = clean(value)
    text = re.sub(r"</?(?:div|p|br|span|li|ul|ol)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def skill_names(item: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ["jobSkillTags", "skillLabel", "showSkillTags"]:
        for tag in item.get(key) or []:
            if isinstance(tag, dict):
                values.append(tag.get("name") or tag.get("value") or tag.get("tag") or tag.get("itemValue"))
            else:
                values.append(tag)
    for tag in get_path(item, ["jobKeyword", "keywords"]) or []:
        if isinstance(tag, dict):
            values.append(tag.get("itemValue"))
    labels = get_path(item, ["jobDetailData", "position", "desc", "labels"])
    if isinstance(labels, list):
        values.extend(labels)
    return unique_text(values)


def parse_salary(item: dict[str, Any]) -> tuple[str, str]:
    salary_real = first(item.get("salaryReal"), get_path(item, ["jobDetailData", "position", "base", "salaryReal"]))
    match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", salary_real)
    if match:
        return salary_number(match.group(1)), salary_number(match.group(2))
    salary_text = first(item.get("salary60"), get_path(item, ["jobDetailData", "position", "base", "salary"]))
    match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*万", salary_text)
    if match:
        return str(int(float(match.group(1)) * 10000)), str(int(float(match.group(2)) * 10000))
    match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", salary_text)
    if match:
        return salary_number(match.group(1)), salary_number(match.group(2))
    return "", ""


def salary_number(value: str) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else value


def location_for(item: dict[str, Any]) -> str:
    parts = unique_text([item.get("workCity"), item.get("cityDistrict"), item.get("streetName"), item.get("tradingArea")])
    if parts:
        return " ".join(parts)
    address = first(get_path(item, ["jobDetailData", "position", "workLocation", "workAddress"]))
    return address.replace("工作地点：", "").strip()


def get_path(obj: Any, path: list[str]) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first(*values: Any) -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return ""


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
