"""Lightweight skill normalization for extracted profiles."""

from __future__ import annotations

from typing import Any


SKILL_ALIASES = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "pytorch": "PyTorch",
    "py torch": "PyTorch",
    "ml": "机器学习",
    "machine learning": "机器学习",
    "机器学习": "机器学习",
    "ai": "人工智能",
    "artificial intelligence": "人工智能",
    "python": "Python",
    "java": "Java",
    "sql": "SQL",
    "nlp": "自然语言处理",
    "natural language processing": "自然语言处理",
}


def normalize_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill in skills:
        name = _clean_text(skill.get("name"))
        if not name:
            continue
        canonical_name = canonical_skill_name(name)
        key = canonical_name.casefold()
        if key in seen:
            _merge_skill(normalized, key, skill)
            continue
        seen.add(key)
        normalized.append(
            {
                **skill,
                "name": canonical_name,
                "raw_name": name,
                "category": _clean_text(skill.get("category")),
                "evidence_ids": _list_of_text(skill.get("evidence_ids")),
            }
        )
    return normalized


def canonical_skill_name(name: str) -> str:
    compact = " ".join(name.strip().split())
    alias_key = compact.casefold()
    return SKILL_ALIASES.get(alias_key, compact)


def _merge_skill(skills: list[dict[str, Any]], key: str, duplicate: dict[str, Any]) -> None:
    for skill in skills:
        if str(skill.get("name", "")).casefold() != key:
            continue
        existing_evidence = list(skill.get("evidence_ids", []))
        for evidence_id in _list_of_text(duplicate.get("evidence_ids")):
            if evidence_id not in existing_evidence:
                existing_evidence.append(evidence_id)
        skill["evidence_ids"] = existing_evidence
        if not skill.get("category") and duplicate.get("category"):
            skill["category"] = _clean_text(duplicate.get("category"))
        return


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
