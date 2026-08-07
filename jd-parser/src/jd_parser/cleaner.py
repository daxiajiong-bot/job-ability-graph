from __future__ import annotations

import re


NAVIGATION_PATTERNS = [
    r"^首页$",
    r"^职位列表$",
    r"^返回顶部$",
    r"^立即申请$",
    r"^申请职位$",
    r"^收藏$",
    r"^分享$",
    r"^举报$",
    r"^登录后查看$",
    r"^查看更多$",
    r"^展开全部$",
]


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def clean_text(raw_text: str) -> str:
    """Deterministically clean JD text without rewriting meaning."""
    text = normalize_newlines(raw_text or "")
    text = re.sub(r"[\t\u00a0]+", " ", text)

    seen_blocks: set[str] = set()
    cleaned_lines: list[str] = []
    blank_pending = False

    for line in text.split("\n"):
        line = re.sub(r"[ ]{2,}", " ", line).strip()
        if not line:
            blank_pending = True
            continue
        if any(re.search(pattern, line, flags=re.I) for pattern in NAVIGATION_PATTERNS):
            continue

        block_key = re.sub(r"\s+", "", line)
        if block_key in seen_blocks:
            continue
        seen_blocks.add(block_key)

        if blank_pending and cleaned_lines:
            cleaned_lines.append("")
        cleaned_lines.append(line)
        blank_pending = False

    return "\n".join(cleaned_lines).strip()

