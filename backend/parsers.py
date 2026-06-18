from __future__ import annotations

import json
import re
from typing import List

from bs4 import BeautifulSoup

from .schemas import JDRecord
from .skill_normalizer import extract_skill_candidates, normalize_skills


def _clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _split_lines(text: str) -> List[str]:
    if not text:
        return []
    items = []
    for part in re.split(r"[\n\r；;]+", text):
        part = re.sub(r"\s+", " ", part).strip(" -•\t\r\n")
        if part:
            items.append(part)
    return items


def parse_zhaopin_search(html: str, source_name: str = "zhaopin") -> List[JDRecord]:
    match = re.search(r"__INITIAL_STATE__=({[\s\S]*?})\s*</script>", html, flags=re.I)
    if not match:
        return []
    state = json.loads(match.group(1))
    items = state.get("positionList", []) or []
    records: List[JDRecord] = []
    for item in items:
        detail = (item.get("jobDetailData") or {}).get("position") or {}
        base = detail.get("base") or {}
        desc = detail.get("desc") or {}
        text = _clean_text(desc.get("description"))
        skills = []
        for s in item.get("skillLabel", []) or []:
            if isinstance(s, dict) and s.get("value"):
                skills.append(s["value"])
        if not skills:
            skills = extract_skill_candidates(text)
        records.append(
            JDRecord(
                source_name=source_name,
                job_title=_clean_text(item.get("name") or base.get("positionName")),
                company_name=_clean_text(item.get("companyName")),
                industry=_clean_text(item.get("industryName")),
                location=_clean_text(item.get("workCity") or item.get("cityDistrict") or base.get("workCity")),
                salary_min=_clean_text(item.get("salaryReal") or base.get("minSalary")),
                salary_max=_clean_text(item.get("salary60") or base.get("maxSalary")),
                experience=_clean_text(item.get("workingExp")),
                education=_clean_text(item.get("education")),
                publish_date=_clean_text(item.get("publishTime") or base.get("publishTime")),
                jd_text=text,
                responsibilities=_split_lines(text),
                requirements=_split_lines(text),
                skills_raw=skills,
                skills_norm=normalize_skills(skills),
                url=_clean_text(item.get("positionUrl") or item.get("positionURL")),
            )
        )
    return records


def parse_lagou_search(html: str, source_name: str = "lagou") -> List[JDRecord]:
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html, flags=re.I)
    if not match:
        return []
    data = json.loads(match.group(1))
    init = (((data.get("props") or {}).get("pageProps") or {}).get("initData") or {})
    content = init.get("content") or {}
    result = (((content.get("positionResult") or {}).get("result")) or [])
    records: List[JDRecord] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("positionDetail") or item.get("positionDesc") or item.get("description"))
        skills = []
        for key in ("skillLables", "positionLables", "industryLables", "companyLabelList"):
            val = item.get(key)
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, str):
                        skills.append(v)
                    elif isinstance(v, dict) and v.get("name"):
                        skills.append(v["name"])
        if not skills:
            skills = extract_skill_candidates(text)
        records.append(
            JDRecord(
                source_name=source_name,
                job_title=_clean_text(item.get("positionName")),
                company_name=_clean_text(item.get("companyShortName") or item.get("companyFullName")),
                industry=_clean_text(item.get("industryField")),
                location=_clean_text(item.get("city")),
                salary_min=_clean_text(item.get("salary")),
                salary_max=_clean_text(item.get("salary")),
                experience=_clean_text(item.get("workYear")),
                education=_clean_text(item.get("education")),
                publish_date=_clean_text(item.get("createTime") or item.get("formatCreateTime")),
                jd_text=text,
                responsibilities=_split_lines(text),
                requirements=_split_lines(text),
                skills_raw=skills,
                skills_norm=normalize_skills(skills),
                url="",
            )
        )
    return records


def parse_public_html_for_jd(html: str, source_name: str, url: str) -> JDRecord:
    soup = BeautifulSoup(html, "lxml")
    title = _clean_text(soup.title.text if soup.title else "")
    body_text = _clean_text(soup.get_text(" "))
    skills = extract_skill_candidates(body_text)
    return JDRecord(
        source_name=source_name,
        job_title=title or url,
        jd_text=body_text[:8000],
        responsibilities=_split_lines(body_text)[:20],
        requirements=_split_lines(body_text)[:20],
        skills_raw=skills,
        skills_norm=normalize_skills(skills),
        url=url,
    )
