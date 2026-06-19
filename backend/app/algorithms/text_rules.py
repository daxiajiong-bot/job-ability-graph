"""Reusable text parsing rules shared by rule-based JD and resume parsers."""

from __future__ import annotations

import datetime as dt
import re
from typing import List, Mapping, Optional, Tuple

from backend.app.algorithms.normalizer import normalize_text
from backend.app.algorithms.skill_catalog import DEGREE_ORDER, DOMAIN_KEYWORDS


def split_items(text: str) -> List[str]:
    items: List[str] = []
    for line in normalize_text(text).splitlines():
        line = line.strip(" -;；,，")
        if not line:
            continue
        fragments = re.split(r"[;；]+", line)
        if len(fragments) == 1 and len(line) > 80:
            fragments = re.split(r"(?<=[。！？!?])", line)
        for fragment in fragments:
            fragment = re.sub(r"^[\-*]+", "", fragment).strip(" -;；,，。")
            if fragment:
                items.append(fragment)
    return items


def parse_section_header(line: str, headers: Mapping[str, str]) -> Tuple[Optional[str], str]:
    normalized = line.strip()
    lowered = normalized.lower()
    for header, section in sorted(headers.items(), key=lambda item: len(item[0]), reverse=True):
        header_lower = header.lower()
        if lowered == header_lower:
            return section, ""
        if lowered.startswith(f"{header_lower}:"):
            return section, normalized.split(":", 1)[1].strip()
        if lowered.startswith(header_lower) and len(normalized) <= len(header) + 4:
            return section, normalized[len(header) :].strip(" :")
    return None, normalized


def chinese_number_to_int(text: str) -> Optional[int]:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return digits.get(text)


def extract_min_year_requirement(text: str) -> Optional[float]:
    normalized = normalize_text(text)
    range_match = re.search(r"(\d+)\s*[-~到至]\s*(\d+)\s*年", normalized)
    if range_match:
        return float(range_match.group(1))
    matches = re.findall(r"(\d+|[一二两三四五六七八九十]+)\s*年(?:以上|及以上|经验|工作经验|开发经验)?", normalized)
    years = [chinese_number_to_int(item) for item in matches]
    years = [item for item in years if item is not None]
    if years:
        return float(min(years))
    return None


def extract_experience_years(text: str) -> float:
    normalized = normalize_text(text)
    explicit_matches = re.findall(r"(\d+|[一二两三四五六七八九十]+)\s*年(?:以上|及以上)?(?:工作|项目|开发|算法|相关)?经验", normalized)
    explicit_years = [chinese_number_to_int(item) for item in explicit_matches]
    explicit_years = [float(item) for item in explicit_years if item is not None]

    total_months = 0
    ranges = re.findall(
        r"((?:19|20)\d{2})(?:[./年-](\d{1,2}))?\s*[-~至到]+\s*((?:19|20)\d{2}|至今|现在|present|now)(?:[./年-](\d{1,2}))?",
        normalized,
        flags=re.IGNORECASE,
    )
    today = dt.date.today()
    for start_year, start_month, end_year, end_month in ranges:
        start_m = int(start_month or 1)
        if re.match(r"(至今|现在|present|now)", end_year, flags=re.IGNORECASE):
            end_y = today.year
            end_m = today.month
        else:
            end_y = int(end_year)
            end_m = int(end_month or 12)
        months = max(0, (end_y - int(start_year)) * 12 + end_m - start_m + 1)
        total_months += months

    range_years = round(total_months / 12, 1) if total_months else 0.0
    return max([0.0, range_years, *explicit_years])


def extract_education(text: str, requirement_mode: bool = False) -> Optional[str]:
    normalized = normalize_text(text)
    if requirement_mode:
        for degree in ("博士", "硕士", "本科", "大专", "专科"):
            if re.search(fr"{degree}\s*(?:及以上|以上|\+)", normalized):
                return "大专" if degree == "专科" else degree
    found: List[Tuple[int, str]] = []
    for degree, rank in DEGREE_ORDER.items():
        if degree in normalized:
            canonical = "大专" if degree == "专科" else "硕士" if degree == "研究生" else degree
            canonical = "博士" if degree == "PhD" else canonical
            found.append((rank, canonical))
    if not found:
        return None
    return sorted(found, reverse=True)[0][1]


def extract_domains(text: str) -> List[str]:
    domains: List[str] = []
    for domain in DOMAIN_KEYWORDS:
        if domain.lower() in text.lower():
            domains.append("招聘业务" if domain == "招聘" else domain)
    return sorted(set(domains))


def infer_job_category(text: str, job_title: str = "") -> str:
    title_rules = [
        ("后端开发岗", ("后端", "服务端", "Java开发", "Python开发")),
        ("前端开发岗", ("前端", "Web前端")),
        ("数据岗", ("数据开发", "数据分析", "大数据", "数仓", "数据仓库")),
        ("算法岗", ("算法", "机器学习", "深度学习", "大模型", "NLP", "推荐")),
        ("产品/运营岗", ("产品", "运营", "增长")),
    ]
    for category, keywords in title_rules:
        if any(keyword.lower() in job_title.lower() for keyword in keywords):
            return category

    combined = f"{job_title}\n{text}"
    rules = [
        ("算法岗", ("算法", "机器学习", "深度学习", "大模型", "NLP", "推荐")),
        ("后端开发岗", ("后端", "服务端", "Java", "Spring", "接口", "微服务")),
        ("前端开发岗", ("前端", "Vue", "React", "JavaScript", "TypeScript")),
        ("数据岗", ("数据分析", "数据开发", "数仓", "数据仓库", "BI", "ETL")),
        ("产品/运营岗", ("产品", "运营", "用户增长")),
    ]
    for category, keywords in rules:
        if any(keyword.lower() in combined.lower() for keyword in keywords):
            return category
    return "通用技术岗"


def local_evidence_clause(text: str, start: int, end: int) -> str:
    """Return the short clause around a skill mention for local rule scoring."""
    left = 0
    right = len(text)
    for index in range(start - 1, -1, -1):
        if text[index] in ",，;；。！？!?":
            left = index + 1
            break
    for index in range(end, len(text)):
        if text[index] in ",，;；。！？!?":
            right = index
            break
    return text[left:right].strip(" -;；,，。")
