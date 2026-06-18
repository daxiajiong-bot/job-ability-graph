from __future__ import annotations

import re
from typing import Iterable, List

from .config import SKILL_SYNONYMS


def normalize_skill(skill: str) -> str:
    token = skill.strip()
    if not token:
        return token
    key = re.sub(r"\s+", "", token.lower())
    return SKILL_SYNONYMS.get(key, SKILL_SYNONYMS.get(token, token))


def normalize_skills(skills: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for skill in skills:
        norm = normalize_skill(skill)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def extract_skill_candidates(text: str) -> List[str]:
    if not text:
        return []
    tokens = set()
    patterns = [
        r"Python3?",
        r"PyTorch",
        r"TensorFlow",
        r"PostgreSQL",
        r"MySQL",
        r"SQL",
        r"Linux",
        r"Docker",
        r"Kubernetes",
        r"RAG",
        r"LLM",
        r"NLP",
        r"机器学习",
        r"深度学习",
        r"数据分析",
        r"数据挖掘",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            tokens.add(m.group(0))
    return sorted(tokens)
