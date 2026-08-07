#!/usr/bin/env python3
"""Expand the local Zhaopin search-page HTML cache.

This script is intentionally cache-only: it writes HTML files under
data/small-raw/_jd_ai_fetch_tmp and never rewrites jd_raw.jsonl/csv/summary.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
REFILL_PATH = REPO_ROOT / "scripts" / "refill_title_ai_jd_data.py"
REBUILD_PATH = REPO_ROOT / "scripts" / "rebuild_strong_ai_jd_data.py"

CORE_CITY_CODES = [
    "all",
    "530",  # 北京
    "538",  # 上海
    "763",  # 广州
    "765",  # 深圳
    "653",  # 杭州
    "801",  # 成都
    "635",  # 南京
    "736",  # 武汉
    "854",  # 西安
    "531",  # 天津
    "639",  # 苏州
    "551",  # 重庆
    "664",  # 合肥
    "702",  # 济南
    "703",  # 青岛
    "600",  # 大连
    "599",  # 沈阳
    "719",  # 郑州
    "749",  # 长沙
    "654",  # 宁波
    "636",  # 无锡
    "682",  # 厦门
    "681",  # 福州
    "768",  # 佛山
    "779",  # 东莞
    "766",  # 珠海
    "780",  # 中山
    "773",  # 惠州
    "638",  # 常州
    "641",  # 南通
    "637",  # 徐州
    "831",  # 昆明
    "691",  # 南昌
    "822",  # 贵阳
    "613",  # 长春
    "622",  # 哈尔滨
    "565",  # 石家庄
    "576",  # 太原
    "785",  # 南宁
    "864",  # 兰州
    "890",  # 乌鲁木齐
    "799",  # 海口
    "587",  # 呼和浩特
    "886",  # 银川
    "878",  # 西宁
    "655",  # 温州
    "656",  # 嘉兴
    "658",  # 绍兴
    "659",  # 金华
    "662",  # 台州
    "707",  # 烟台
    "708",  # 潍坊
    "685",  # 泉州
    "645",  # 扬州
    "646",  # 镇江
    "665",  # 芜湖
    "721",  # 洛阳
    "740",  # 襄阳
    "739",  # 宜昌
]

LONGTAIL_KEYWORDS = [
    "CUDA工程师",
    "vLLM",
    "SGLang",
    "LoRA微调",
    "模型微调",
    "模型量化",
    "模型压缩",
    "推理优化工程师",
    "AI平台工程师",
    "训练平台工程师",
    "机器学习平台工程师",
    "向量数据库",
    "Milvus",
    "LlamaIndex",
    "LangChain",
    "LangGraph",
    "AutoGen",
    "MCP开发",
    "提示词工程师",
    "AIGC算法",
    "生成式AI算法",
    "Diffusion算法",
    "文生图算法",
    "视频生成算法",
    "多模态算法",
    "图像分割算法",
    "目标检测算法",
    "点云算法",
    "感知算法",
    "自动驾驶感知算法",
    "语音合成算法",
    "语音识别算法",
    "ASR算法",
    "TTS算法",
    "排序算法",
    "召回算法",
    "推荐算法",
    "搜索算法",
    "广告算法",
    "风控算法",
    "反欺诈算法",
    "预测算法",
    "异常检测算法",
    "数字人算法",
    "知识图谱工程师",
    "RAG工程师",
    "Agent工程师",
    "大模型应用开发",
]
BROAD_TECH_KEYWORDS = [
    "AI软件工程师",
    "AI系统工程师",
    "AI后端开发",
    "AI全栈开发",
    "AI应用开发工程师",
    "AI应用研发",
    "AI平台开发",
    "AI平台研发",
    "AI基础设施",
    "AI Infra工程师",
    "AI编译器工程师",
    "AIGC开发工程师",
    "AIGC应用开发",
    "大模型后端开发",
    "大模型应用工程师",
    "大模型应用研发",
    "大模型平台开发",
    "大模型平台工程师",
    "大模型训练工程师",
    "大模型推理工程师",
    "大模型部署工程师",
    "大模型微调工程师",
    "大模型工程化",
    "大模型解决方案开发",
    "LLM应用开发",
    "LLM平台工程师",
    "LLMOps",
    "MLOps工程师",
    "模型工程师",
    "模型部署工程师",
    "模型推理工程师",
    "模型训练工程师",
    "模型优化工程师",
    "模型服务工程师",
    "推理平台工程师",
    "训练平台开发",
    "算法平台工程师",
    "算法平台开发",
    "机器学习平台开发",
    "数据科学家",
    "数据科学工程师",
    "数据挖掘算法",
    "数据挖掘工程师",
    "推荐系统工程师",
    "推荐系统研发",
    "推荐算法研发",
    "搜索推荐算法",
    "搜索算法研发",
    "排序算法工程师",
    "召回算法工程师",
    "广告算法工程师",
    "风控算法工程师",
    "反欺诈算法工程师",
    "预测算法工程师",
    "异常检测工程师",
    "NLP算法工程师",
    "NLP研发工程师",
    "自然语言处理研发",
    "语音算法工程师",
    "语音识别工程师",
    "语音合成工程师",
    "ASR工程师",
    "TTS工程师",
    "OCR算法工程师",
    "OCR工程师",
    "计算机视觉研发",
    "视觉感知工程师",
    "视觉软件工程师",
    "图像识别算法工程师",
    "图像处理工程师",
    "图像分割工程师",
    "目标检测工程师",
    "点云算法工程师",
    "自动驾驶算法工程师",
    "自动驾驶感知工程师",
    "智能驾驶算法工程师",
    "智能座舱算法工程师",
    "机器人算法工程师",
    "SLAM算法工程师",
    "强化学习算法工程师",
    "知识图谱研发",
    "知识图谱算法工程师",
    "RAG开发工程师",
    "RAG应用开发",
    "Agent开发工程师",
    "Agent应用开发",
    "智能体开发工程师",
    "智能体应用开发",
    "PyTorch工程师",
    "TensorFlow工程师",
    "Triton工程师",
    "CUDA开发工程师",
    "GPU算法工程师",
    "GPU推理优化",
    "AI4S算法工程师",
    "AIDD算法工程师",
]
HIGH_YIELD_BROADTECH_KEYWORDS = [
    "AI Infra工程师",
    "AI应用开发工程师",
    "AI应用研发",
    "智能体开发工程师",
    "视觉软件工程师",
    "大模型应用工程师",
    "大模型应用研发",
    "机器人算法工程师",
    "AI全栈开发",
    "图像处理工程师",
    "AI软件工程师",
    "SLAM算法工程师",
    "AI后端开发",
    "自动驾驶算法工程师",
    "AI系统工程师",
    "图像识别算法工程师",
    "Agent应用开发",
    "点云算法工程师",
    "预测算法工程师",
    "强化学习算法工程师",
    "智能驾驶算法工程师",
    "目标检测工程师",
    "AI平台开发",
    "自动驾驶感知工程师",
    "AI平台研发",
    "LLM应用开发",
    "大模型微调工程师",
    "视觉感知工程师",
    "语音算法工程师",
    "智能体应用开发",
    "计算机视觉研发",
    "知识图谱研发",
    "知识图谱算法工程师",
    "算法平台工程师",
    "NLP研发工程师",
    "大模型后端开发",
    "大模型训练工程师",
    "数据挖掘算法",
    "模型训练工程师",
    "风控算法工程师",
]
REFILL_KEYWORDS = [*LONGTAIL_KEYWORDS, *BROAD_TECH_KEYWORDS]


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword-set", choices=["core", "longtail", "broadtech", "highyield", "all"], default="longtail")
    parser.add_argument("--cities", choices=["core", "cached", "all"], default="core")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-page", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many tasks; 0 means no limit.")
    parser.add_argument("--min-cache-bytes", type=int, default=50_000)
    parser.add_argument("--request-timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--parse-positions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--refetch-unusable", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true", help="Refetch even when an existing usable cache file exists.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.start_page < 1 or args.max_page < args.start_page:
        raise SystemExit("--start-page and --max-page are invalid")

    helper = load_module(HELPER_PATH, "append_ai_jd_data_expand_cache")
    refill = load_module(REFILL_PATH, "refill_title_ai_jd_data_expand_cache")
    rebuild = load_module(REBUILD_PATH, "rebuild_strong_ai_jd_data_expand_cache")

    keywords = select_keywords(args.keyword_set, refill, rebuild)
    city_codes = select_city_codes(args.cities)
    tasks = build_tasks(keywords, city_codes, args.start_page, args.max_page)
    if args.limit > 0:
        tasks = tasks[: args.limit]

    print(
        json.dumps(
            {
                "plan": {
                    "cache_root": str(FETCH_ROOT),
                    "keyword_set": args.keyword_set,
                    "keyword_count": len(keywords),
                    "cities": args.cities,
                    "city_count": len(city_codes),
                    "start_page": args.start_page,
                    "max_page": args.max_page,
                    "tasks": len(tasks),
                    "dry_run": args.dry_run,
                }
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "sample_tasks": [
                        {"keyword": task.keyword, "city_code": task.city_code, "page": task.page, "url": task.url}
                        for task in tasks[:20]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return 0

    FETCH_ROOT.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {
        "tasks": len(tasks),
        "completed": 0,
        "skipped_existing_large": 0,
        "skipped_existing_small": 0,
        "skipped_existing_unusable": 0,
        "fetched_usable": 0,
        "fetched_unusable": 0,
        "fetch_failed": 0,
        "parse_pages": 0,
        "positions_seen": 0,
        "bytes_written": 0,
    }
    start = time.time()
    parse_positions = helper.parse_positions if args.parse_positions else None
    worker_count = max(1, args.workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                process_task,
                task,
                args.min_cache_bytes,
                args.force,
                args.refetch_unusable,
                args.request_timeout,
                args.retries,
                parse_positions,
            )
            for task in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            stats["completed"] += 1
            status = result["status"]
            if status in stats:
                stats[status] += 1
            if result.get("parsed"):
                stats["parse_pages"] += 1
            stats["positions_seen"] += int(result.get("positions") or 0)
            stats["bytes_written"] += int(result.get("bytes_written") or 0)
            if stats["completed"] % max(1, args.progress_every) == 0 or stats["completed"] == len(tasks):
                print(
                    json.dumps(
                        {
                            "progress": {
                                **stats,
                                "elapsed_seconds": round(time.time() - start, 1),
                            }
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    print(
        json.dumps(
            {
                "status": "ok",
                "summary": {
                    **stats,
                    "elapsed_seconds": round(time.time() - start, 1),
                    "cache_root": str(FETCH_ROOT),
                },
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


def select_keywords(keyword_set: str, refill: Any, rebuild: Any) -> list[str]:
    core = unique_clean([*getattr(refill, "FETCH_KEYWORDS", []), *getattr(rebuild, "STRONG_KEYWORDS", [])])
    if keyword_set == "core":
        return core
    if keyword_set == "longtail":
        return unique_clean(LONGTAIL_KEYWORDS)
    if keyword_set == "broadtech":
        return unique_clean(BROAD_TECH_KEYWORDS)
    if keyword_set == "highyield":
        return unique_clean(HIGH_YIELD_BROADTECH_KEYWORDS)
    return unique_clean([*core, *LONGTAIL_KEYWORDS, *BROAD_TECH_KEYWORDS])


def select_city_codes(mode: str) -> list[str]:
    if mode == "core":
        return CORE_CITY_CODES
    cached = discover_cached_city_codes()
    if mode == "cached":
        return cached
    return unique_clean([*CORE_CITY_CODES, *cached])


def discover_cached_city_codes() -> list[str]:
    codes = set[str]()
    pattern = re.compile(r"(?P<city>\d+|all)_.+_\d+\.html$")
    for path in FETCH_ROOT.glob("*.html"):
        match = pattern.match(path.name)
        if match:
            codes.add(match.group("city"))
    return sorted(codes, key=city_sort_key)


def build_tasks(keywords: list[str], city_codes: list[str], start_page: int, max_page: int) -> list[CacheTask]:
    return [
        CacheTask(keyword=keyword, city_code=city_code, page=page)
        for page in range(start_page, max_page + 1)
        for keyword in keywords
        for city_code in city_codes
    ]


def process_task(
    task: CacheTask,
    min_cache_bytes: int,
    force: bool,
    refetch_unusable: bool,
    request_timeout: int,
    retries: int,
    parse_positions: Callable[[str], list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    existing = classify_cache(task.cache_path, min_cache_bytes)
    if existing["usable"] and not force:
        result = {
            "task": task_key(task),
            "status": "skipped_existing_large" if existing["large"] else "skipped_existing_small",
            "parsed": 0,
            "positions": 0,
            "bytes_written": 0,
        }
        if parse_positions is not None:
            html = task.cache_path.read_text(encoding="utf-8", errors="replace")
            positions = parse_positions(html)
            result["parsed"] = int(bool(positions))
            result["positions"] = len(positions)
        return result
    if existing["exists"] and not existing["usable"] and not refetch_unusable:
        return {
            "task": task_key(task),
            "status": "skipped_existing_unusable",
            "parsed": 0,
            "positions": 0,
            "bytes_written": 0,
        }

    html = fetch_zhaopin_html(task.url, timeout_seconds=request_timeout, retries=retries)
    if not html:
        return {
            "task": task_key(task),
            "status": "fetch_failed",
            "parsed": 0,
            "positions": 0,
            "bytes_written": 0,
        }
    if not is_usable_zhaopin_html(html):
        return {
            "task": task_key(task),
            "status": "fetched_unusable",
            "parsed": 0,
            "positions": 0,
            "bytes_written": 0,
        }

    task.cache_path.parent.mkdir(parents=True, exist_ok=True)
    task.cache_path.write_text(html, encoding="utf-8")
    positions = parse_positions(html) if parse_positions is not None else []
    return {
        "task": task_key(task),
        "status": "fetched_usable",
        "parsed": int(bool(positions)),
        "positions": len(positions),
        "bytes_written": task.cache_path.stat().st_size,
    }


def classify_cache(path: Path, min_cache_bytes: int) -> dict[str, bool]:
    if not path.exists():
        return {"exists": False, "usable": False, "large": False}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"exists": True, "usable": False, "large": False}
    return {
        "exists": True,
        "usable": is_usable_zhaopin_html(text),
        "large": path.stat().st_size >= min_cache_bytes,
    }


def fetch_zhaopin_html(url: str, timeout_seconds: int, retries: int) -> str:
    ps_command = (
        "$ProgressPreference='SilentlyContinue'; "
        f"$uri='{url}'; "
        "$headers=@{"
        "'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36';"
        "'Accept-Language'='zh-CN,zh;q=0.9';"
        "'Referer'='https://sou.zhaopin.com/'"
        "}; "
        f"(Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $headers -TimeoutSec {timeout_seconds}).Content"
    )
    for attempt in range(max(1, retries + 1)):
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds + 20,
            )
            return completed.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt + 1 < max(1, retries + 1):
                time.sleep(1.5 * (attempt + 1))
    return ""


def is_usable_zhaopin_html(text: str) -> bool:
    return '"positionList"' in text or "__INITIAL_STATE__" in text


def unique_clean(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or "\ufffd" in text or "?" in text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def city_sort_key(value: str) -> tuple[int, str]:
    return (0, value) if value == "all" else (1, value)


def task_key(task: CacheTask) -> dict[str, Any]:
    return {"keyword": task.keyword, "city_code": task.city_code, "page": task.page}


if __name__ == "__main__":
    raise SystemExit(main())
