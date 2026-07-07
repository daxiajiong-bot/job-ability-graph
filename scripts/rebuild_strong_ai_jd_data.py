#!/usr/bin/env python3
"""Rebuild JD data with only strongly AI/ML-related positions."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"

STRONG_KEYWORDS = [
    "机器学习",
    "深度学习",
    "大模型",
    "算法工程师",
    "AI算法",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "视觉算法",
    "推荐算法",
    "搜索算法",
    "数据挖掘",
    "多模态",
    "LLM",
    "PyTorch",
    "TensorFlow",
    "模型训练",
    "模型微调",
    "RAG",
    "知识图谱",
    "强化学习",
    "目标检测",
    "语音识别",
    "机器视觉",
    "人工智能研发",
    "AI工程师",
    "大模型应用开发",
]

CORE_TERMS = [
    "机器学习",
    "深度学习",
    "大模型",
    "算法",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "视觉算法",
    "推荐算法",
    "搜索算法",
    "语音算法",
    "数据挖掘",
    "多模态",
    "LLM",
    "PyTorch",
    "TensorFlow",
    "模型训练",
    "模型微调",
    "模型部署",
    "模型推理",
    "推理优化",
    "微调",
    "RAG",
    "强化学习",
    "知识图谱",
    "目标检测",
    "语音识别",
    "机器视觉",
    "数据科学",
    "智能算法",
    "AIGC算法",
    "生成式AI算法",
    "Machine Learning",
    "ML Engineer",
    "Deep Learning",
    "Artificial Intelligence",
    "AI Engineer",
    "AI Scientist",
    "Applied Scientist",
    "Large Language",
    "Natural Language Processing",
    "Computer Vision",
    "Data Scientist",
    "Data Science",
    "Model Training",
    "Model Deployment",
    "MLOps",
    "GenAI",
    "Generative AI",
    "Reinforcement Learning",
    "Recommender",
]

TITLE_STRONG_TERMS = [
    "算法",
    "机器学习",
    "深度学习",
    "大模型",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "视觉算法",
    "推荐算法",
    "搜索算法",
    "语音算法",
    "数据挖掘",
    "多模态",
    "LLM",
    "模型训练",
    "模型微调",
    "RAG",
    "强化学习",
    "知识图谱",
    "目标检测",
    "机器视觉",
    "AI研发",
    "人工智能研发",
    "AI工程师",
    "人工智能工程师",
    "AI应用工程师",
    "AI开发工程师",
    "AIGC算法",
    "AIGC工程师",
    "AI Agent工程师",
    "AI Agent 产品",
    "AI产品经理",
    "AI 产品经理",
    "大模型产品经理",
    "人工智能产品经理",
    "大模型评测",
    "大模型数据",
    "数据标注工程师",
    "模型评测",
    "AI平台",
    "AI安全",
    "AI应用",
    "AI自动化",
    "AI全栈",
    "AI原生产品",
    "AI产品负责人",
    "AI互联网产品经理",
    "AI项目经理",
    "AI 项目经理",
    "人工智能项目经理",
    "人工智能程序员",
    "人工智能技术助理",
    "人工智能测试",
    "人工智能产品调测",
    "人工智能与无线通信",
    "电力人工智能",
    "人工智能研究",
    "材料人工智能",
    "Pytorch",
    "视觉专家",
    "端侧 AI",
    "AI大模型",
    "大模型全链路",
    "AI Agent 研发",
    "提示词工程师",
    "数据科学家",
    "Machine Learning",
    "ML Engineer",
    "Deep Learning",
    "AI Engineer",
    "AI Scientist",
    "Applied Scientist",
    "Data Scientist",
    "Computer Vision",
    "MLOps",
    "GenAI",
    "Generative AI",
]

TECH_TITLE_TERMS = [
    "工程师",
    "开发",
    "研发",
    "研究员",
    "科学家",
    "架构师",
    "技术专家",
    "博士后",
    "实习生",
    "Engineer",
    "Scientist",
    "Researcher",
    "Developer",
    "Architect",
    "MLOps",
    "Data Engineer",
    "Applied Scientist",
]

WEAK_TITLE_TERMS = [
    "前端",
    "后端",
    "全栈",
    "软件测试",
    "测试开发",
    "测试工程师",
    "测试助理",
    "测试",
    "Frontend",
    "Front End",
    "Backend",
    "Back End",
    "Full Stack",
    "Fullstack",
    "QA",
    "Quality Engineer",
    "Test Engineer",
    "Testing",
    "SDET",
    "销售",
    "售前",
    "售后",
    "顾问",
    "咨询",
    "客服",
    "运营",
    "产品经理",
    "产品负责人",
    "项目经理",
    "项目管理",
    "项目主管",
    "数据标注",
    "标注",
    "训练师",
    "音频转写",
    "对话改写",
    "内容审核",
    "数据分析师",
    "行政",
    "兼职",
    "暑假工",
    "教师",
    "老师",
    "讲师",
    "助教",
    "招生",
    "市场",
    "商务",
    "编导",
    "导演",
    "短剧",
    "设计师",
    "画师",
    "美工",
    "主播",
    "文案",
    "剪辑",
    "视频制作",
    "内容制作",
    "管培",
    "课程",
    "教培",
    "外观结构",
    "Sales",
    "Marketing",
    "Customer",
    "Support",
    "Account Executive",
    "Recruiter",
    "Copywriter",
    "Content",
    "Designer",
    "Product Manager",
    "Product Owner",
    "Project Manager",
    "Program Manager",
    "Data Analyst",
    "Business Analyst",
    "Product Analyst",
    "Marketing Analyst",
    "Financial Analyst",
    "Operations Analyst",
    "Business Intelligence",
    "Community",
    "SEO",
    "Coordinator",
    "Assistant",
]

def term_pattern(term: str) -> str:
    escaped = re.escape(term)
    if re.search(r"[A-Za-z]", term):
        return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return escaped


CORE_RE = re.compile("|".join(term_pattern(term) for term in CORE_TERMS), re.IGNORECASE)
TITLE_STRONG_RE = re.compile("|".join(term_pattern(term) for term in TITLE_STRONG_TERMS), re.IGNORECASE)
TECH_TITLE_RE = re.compile("|".join(term_pattern(term) for term in TECH_TITLE_TERMS), re.IGNORECASE)
WEAK_TITLE_RE = re.compile("|".join(term_pattern(term) for term in WEAK_TITLE_TERMS), re.IGNORECASE)

REQUIRED_TITLE_TERMS = [
    "人工智能",
    "机器学习",
    "算法",
    "大模型",
    "大语言模型",
    "自然语言处理",
    "计算机视觉",
    "NLP",
    "CV",
    "LLM",
    "深度学习",
    "AI",
    "Machine Learning",
    "ML",
    "Algorithm",
    "Algorithms",
    "Deep Learning",
    "Large Language Model",
    "Large Language Models",
    "Natural Language Processing",
    "Computer Vision",
    "Artificial Intelligence",
    "AI/ML",
    "AIML",
]

REQUIRED_TITLE_RE = re.compile("|".join(term_pattern(term) for term in REQUIRED_TITLE_TERMS), re.IGNORECASE)

AI_DOMAIN_TERMS = [
    "人工智能",
    "机器学习",
    "深度学习",
    "大模型",
    "大语言模型",
    "自然语言处理",
    "计算机视觉",
    "机器视觉",
    "图像算法",
    "视觉算法",
    "图像识别",
    "目标检测",
    "多模态",
    "推荐算法",
    "搜索算法",
    "搜索/推荐",
    "强化学习",
    "知识图谱",
    "语音识别",
    "神经网络",
    "智能算法",
    "数据挖掘",
    "模型训练",
    "模型微调",
    "模型部署",
    "模型推理",
    "智能体",
    "AI",
    "AIGC",
    "NLP",
    "CV",
    "LLM",
    "RAG",
    "Agent",
    "PyTorch",
    "TensorFlow",
    "Transformer",
    "Machine Learning",
    "Deep Learning",
    "Artificial Intelligence",
    "Computer Vision",
    "Natural Language Processing",
    "Generative AI",
    "GenAI",
    "Reinforcement Learning",
]

ENGINEERING_TITLE_TERMS = [
    "工程师",
    "开发",
    "研发",
    "算法",
    "研究员",
    "研究",
    "博士后",
    "科学家",
    "架构师",
    "专家",
    "技术",
    "技术专家",
    "建模",
    "Engineer",
    "Developer",
    "Scientist",
    "Researcher",
    "Architect",
]

NON_AI_TECH_TITLE_TERMS = [
    "电机控制",
    "伺服",
    "无线通信",
    "通信算法",
    "调度算法",
    "AGV",
    "运筹优化",
    "仿真算法",
    "数控算法",
    "FPGA",
    "CT算法",
    "重建",
    "信号处理",
    "地图算法",
    "导航算法",
    "定位算法",
    "卫星",
    "机械臂控制",
    "工业机器人",
    "ISP算法",
    "SLAM",
    "ROS",
]

AI_DOMAIN_RE = re.compile("|".join(term_pattern(term) for term in AI_DOMAIN_TERMS), re.IGNORECASE)
ENGINEERING_TITLE_RE = re.compile("|".join(term_pattern(term) for term in ENGINEERING_TITLE_TERMS), re.IGNORECASE)
NON_AI_TECH_TITLE_RE = re.compile("|".join(term_pattern(term) for term in NON_AI_TECH_TITLE_TERMS), re.IGNORECASE)
NONTECH_EVAL_RE = re.compile(r"训练|测评|评测|评估|测试")

THEMUSE_LOCATIONS = [
    "Remote",
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "Austin, TX",
    "Boston, MA",
    "Chicago, IL",
    "Los Angeles, CA",
    "Washington, DC",
    "Atlanta, GA",
    "Dallas, TX",
    "Denver, CO",
    "Toronto, Canada",
    "Vancouver, Canada",
    "London, United Kingdom",
    "Berlin, Germany",
    "Paris, France",
    "Amsterdam, Netherlands",
    "Dublin, Ireland",
    "Singapore",
    "Bengaluru, India",
    "Hyderabad, India",
    "Tokyo, Japan",
    "Sydney, Australia",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=3000)
    parser.add_argument("--max-pages-per-query-city", type=int, default=30)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--skip-zhaopin", action="store_true")
    args = parser.parse_args()

    helper = load_helper()
    helper.FETCH_ROOT.mkdir(parents=True, exist_ok=True)
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    existing_rows = helper.read_jsonl(JD_JSONL) if JD_JSONL.exists() else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {
        "existing_before": len(existing_rows),
        "existing_kept": 0,
        "existing_rejected": 0,
        "pages_attempted": 0,
        "pages_parsed": 0,
        "pages_failed": 0,
        "positions_seen": 0,
        "duplicate_skipped": 0,
        "missing_id_skipped": 0,
        "old_skipped": 0,
        "weak_skipped": 0,
        "foreign_skipped": 0,
    }

    for row in existing_rows:
        job_id = row.get("job_id")
        if job_id is None:
            stats["existing_rejected"] += 1
            continue
        if row.get("source_name") != "zhaopin":
            stats["existing_rejected"] += 1
            stats["foreign_skipped"] += 1
            continue
        key = str(job_id)
        if key in seen:
            stats["duplicate_skipped"] += 1
            continue
        if helper.is_recent(str(row.get("publish_date") or ""), cutoff) and is_strong_ai_ml_related(row):
            rows.append(row)
            seen.add(key)
            stats["existing_kept"] += 1
            if len(rows) >= args.target_total:
                break
        else:
            stats["existing_rejected"] += 1

    used_tasks: list[dict[str, Any]] = []
    if len(rows) < args.target_total and not args.skip_zhaopin:
        for task in iter_tasks(helper, args.max_pages_per_query_city):
            if len(rows) >= args.target_total:
                break
            stats["pages_attempted"] += 1
            html = helper.fetch_html(task, cache_only=args.cache_only)
            if not html:
                stats["pages_failed"] += 1
                continue
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
            items = helper.parse_positions(html)
            if not items:
                continue
            stats["pages_parsed"] += 1
            stats["positions_seen"] += len(items)
            used_tasks.append(
                {
                    "keyword": task.keyword,
                    "city": task.city_name,
                    "city_code": task.city_code,
                    "page": task.page,
                }
            )

            for item in items:
                if len(rows) >= args.target_total:
                    break
                job_id = item.get("jobId")
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
                if not is_strong_ai_ml_related(row):
                    stats["weak_skipped"] += 1
                    continue
                rows.append(row)
                seen.add(key)

            if stats["pages_attempted"] % 50 == 0 or len(rows) >= args.target_total:
                print(
                    json.dumps(
                        {
                            "progress": {
                                "total_rows": len(rows),
                                "target_total": args.target_total,
                                "pages_attempted": stats["pages_attempted"],
                                "pages_parsed": stats["pages_parsed"],
                                "positions_seen": stats["positions_seen"],
                            }
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    if len(rows) < args.target_total:
        raise SystemExit(
            json.dumps(
                {
                    "status": "insufficient_domestic_strong_ai_ml_rows",
                    "collected": len(rows),
                    "target_total": args.target_total,
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rows[: args.target_total]
    rows = sort_rows(rows)
    write_jsonl(JD_JSONL, rows)
    write_csv(JD_CSV, rows, helper.CSV_FIELDS)
    update_summary(
        helper=helper,
        rows=rows,
        stats=stats,
        used_tasks=used_tasks,
        scrape_time=scrape_time,
        recent_since=args.recent_since,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "total_after": len(rows),
                "unique_job_ids": len({str(row.get("job_id")) for row in rows}),
                "first_job_id": rows[0]["job_id"],
                "last_job_id": rows[-1]["job_id"],
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("append_ai_jd_data", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load helper: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def iter_tasks(helper: Any, max_pages: int) -> list[Any]:
    tasks = []
    for page in range(1, max_pages + 1):
        for keyword in STRONG_KEYWORDS:
            for city_code, city_name in helper.CITIES.items():
                tasks.append(helper.FetchTask(keyword=keyword, city_code=city_code, city_name=city_name, page=page))
    return tasks


def iter_themuse_jobs(categories: list[str], max_pages: int, workers: int, locations: list[str]) -> Any:
    tasks = [
        (category, page, location)
        for category in [item.strip() for item in categories if item.strip()]
        for location in locations
        for page in range(1, max_pages + 1)
    ]
    chunk_size = max(1, workers) * 8
    for start in range(0, len(tasks), chunk_size):
        chunk = tasks[start : start + chunk_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(fetch_themuse_page, task) for task in chunk]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result.get("error"):
                    print(json.dumps({"themuse_fetch_failed": result}, ensure_ascii=False), flush=True)
                    continue
                for job in result.get("jobs") or []:
                    if isinstance(job, dict):
                        yield job, result["page"], result["category"]


def fetch_themuse_page(task: tuple[str, int, str]) -> dict[str, Any]:
    category, page, location = task
    url = f"https://www.themuse.com/api/public/jobs?page={page}&category={quote(category)}"
    if location:
        url += f"&location={quote(location)}"
    for attempt in range(3):
        try:
            payload = json.loads(
                urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 Codex"}), timeout=30).read().decode("utf-8")
            )
            break
        except HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"category": category, "page": page, "location": location, "error": str(exc), "jobs": []}
        except Exception as exc:
            return {"category": category, "page": page, "location": location, "error": str(exc), "jobs": []}
    return {"category": category, "page": page, "location": location, "jobs": payload.get("results") or []}


def convert_themuse_job(job: dict[str, Any], page: int, category: str, scrape_time: str) -> dict[str, Any]:
    tags = tag_names(job.get("tags")) + tag_names(job.get("categories"))
    locations = tag_names(job.get("locations"))
    company = job.get("company") if isinstance(job.get("company"), dict) else {}
    description = normalize_html(job.get("contents"))
    lines = split_lines(description)
    return {
        "source_type": "job_platform",
        "source_name": "themuse",
        "page": page,
        "job_id": f"themuse_{job.get('id')}",
        "job_title": clean(job.get("name")),
        "company_name": clean(company.get("name")),
        "industry": category,
        "location": ", ".join(locations),
        "salary_min": "",
        "salary_max": "",
        "experience": "",
        "education": "",
        "publish_date": clean(job.get("publication_date"))[:10],
        "jd_text": description,
        "responsibilities": lines,
        "requirements": lines,
        "skills_raw": tags,
        "skills_norm": tags,
        "url": ((job.get("refs") or {}).get("landing_page") if isinstance(job.get("refs"), dict) else "") or "",
        "scrape_time": scrape_time,
    }


def tag_names(values: Any) -> list[str]:
    names: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            text = clean(value.get("name") or value.get("short_name"))
        else:
            text = clean(value)
        if text:
            names.append(text)
    return names


def normalize_html(value: Any) -> str:
    text = clean(value)
    text = re.sub(r"</?(?:div|p|br|span|li|ul|ol|h1|h2|h3|h4|strong|em)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"\r?\n+", text) if line.strip()]


def is_themuse_recent(value: str, cutoff: datetime) -> bool:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) >= cutoff
    except ValueError:
        return False


def is_strong_ai_ml_related(row: dict[str, Any]) -> bool:
    title = str(row.get("job_title") or "")
    text = row_text(row)
    if row.get("source_name") != "zhaopin":
        return False
    if WEAK_TITLE_RE.search(title):
        return False
    if NONTECH_EVAL_RE.search(title) and not ENGINEERING_TITLE_RE.search(title):
        return False
    if NON_AI_TECH_TITLE_RE.search(title) and not AI_DOMAIN_RE.search(text):
        return False
    domain_count = sum(1 for term in AI_DOMAIN_TERMS if re.search(term_pattern(term), text, re.IGNORECASE))
    title_has_domain = bool(REQUIRED_TITLE_RE.search(title) or AI_DOMAIN_RE.search(title))
    if not ENGINEERING_TITLE_RE.search(title) and not (title_has_domain and domain_count >= 4):
        return False
    return title_has_domain


def row_text(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("job_title") or ""),
        str(row.get("industry") or ""),
        str(row.get("jd_text") or ""),
        str(row.get("company_name") or ""),
    ]
    for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
        value = row.get(key) or []
        pieces.append(" ".join(map(str, value)) if isinstance(value, list) else str(value))
    return " ".join(pieces)


def core_term_count(text: str) -> int:
    return sum(1 for term in CORE_TERMS if re.search(term_pattern(term), text, re.IGNORECASE))


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("job_title") or "").casefold(),
            str(row.get("company_name") or "").casefold(),
            str(row.get("location") or "").casefold(),
            str(row.get("job_id") or ""),
        ),
    )


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


def update_summary(
    *,
    helper: Any,
    rows: list[dict[str, Any]],
    stats: dict[str, int],
    used_tasks: list[dict[str, Any]],
    scrape_time: str,
    recent_since: str,
) -> None:
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    source_counts: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source_name") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
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
        "source": "zhaopin_search_page",
        "topic": "domestic strong AI/ML technical jobs only",
        "keywords": STRONG_KEYWORDS,
        "cities": list(helper.CITIES.values()),
        "fallback_source": None,
        "source_counts": source_counts,
        "recent_since": recent_since,
        "total_after": len(rows),
        "sort": "job_title, company_name, location, job_id",
        "scrape_time": scrape_time,
        "filter": {
            "required_title_terms": REQUIRED_TITLE_TERMS,
            "core_terms": CORE_TERMS,
            "title_strong_terms": TITLE_STRONG_TERMS,
            "weak_title_terms": WEAK_TITLE_TERMS,
            "engineering_title_terms": ENGINEERING_TITLE_TERMS,
            "domestic_only": True,
        },
        "stats": stats,
        "used_task_count": len(used_tasks),
        "first_tasks": used_tasks[:20],
        "last_tasks": used_tasks[-20:],
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
