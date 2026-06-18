from __future__ import annotations

import time
from typing import List

import requests

from .config import SourceConfig
from .parsers import parse_lagou_search, parse_public_html_for_jd, parse_zhaopin_search
from .schemas import JDRecord


DEFAULT_HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 20) -> str:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_zhaopin_records(source: SourceConfig, keyword: str, target_count: int = 20) -> List[JDRecord]:
    records: List[JDRecord] = []
    for page in range(source.page_start, source.max_pages + 1):
        url = source.search_url_template.format(keyword=keyword, page=page)
        try:
            html = fetch_html(url)
        except Exception:
            continue
        page_records = parse_zhaopin_search(html, source_name=source.name)
        if not page_records:
            break
        records.extend(page_records)
        if len(records) >= target_count:
            break
        time.sleep(0.5)
    return records[:target_count]


def fetch_lagou_records(source: SourceConfig, keyword: str, target_count: int = 20) -> List[JDRecord]:
    records: List[JDRecord] = []
    for page in range(source.page_start, source.max_pages + 1):
        url = source.search_url_template.format(keyword=keyword, page=page)
        try:
            html = fetch_html(url)
        except Exception:
            continue
        page_records = parse_lagou_search(html, source_name=source.name)
        if not page_records:
            fallback = parse_public_html_for_jd(html, source.name, url)
            if fallback.jd_text:
                page_records = [fallback]
        records.extend(page_records)
        if len(records) >= target_count:
            break
        time.sleep(0.5)
    return records[:target_count]


def fetch_public_page(url: str, source_name: str = "official_site") -> JDRecord:
    html = fetch_html(url)
    return parse_public_html_for_jd(html, source_name=source_name, url=url)


def fetch_source_records(source: SourceConfig, keyword: str, target_count: int = 20) -> List[JDRecord]:
    try:
        if source.name == "zhaopin":
            return fetch_zhaopin_records(source, keyword, target_count)
        if source.name == "lagou":
            return fetch_lagou_records(source, keyword, target_count)
    except Exception:
        return []
    return []
