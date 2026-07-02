"""ESCO-backed skill normalization for extracted profiles."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.app.data_governance.esco import EscoConcept, EscoIndex


def normalize_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = _esco_index()
    for skill in skills:
        raw_name = _clean_text(skill.get("raw_name") or skill.get("name"))
        if not raw_name:
            continue
        concept = _link_exact_label(index, raw_name)
        name = concept.preferred_label if concept is not None else raw_name
        key = (concept.esco_uri if concept is not None else name).casefold()
        if key in seen:
            _merge_skill(normalized, key, skill)
            continue
        seen.add(key)
        normalized.append(
            {
                **skill,
                "name": name,
                "raw_name": raw_name,
                "category": _clean_text(skill.get("category")),
                "evidence_ids": _list_of_text(skill.get("evidence_ids")),
                "esco_uri": concept.esco_uri if concept is not None else None,
                "esco_preferred_label": concept.preferred_label if concept is not None else None,
                "esco_version": concept.version if concept is not None else None,
                "linking_status": "linked" if concept is not None else "unmapped",
                "linking_confidence": 1.0 if concept is not None else 0.0,
            }
        )
    return normalized


def _link_exact_label(index: EscoIndex, value: str) -> EscoConcept | None:
    return index.exact_label_match(value)


def _merge_skill(skills: list[dict[str, Any]], key: str, duplicate: dict[str, Any]) -> None:
    for skill in skills:
        skill_key = str(skill.get("esco_uri") or skill.get("name", "")).casefold()
        if skill_key != key:
            continue
        existing_evidence = list(skill.get("evidence_ids", []))
        for evidence_id in _list_of_text(duplicate.get("evidence_ids")):
            if evidence_id not in existing_evidence:
                existing_evidence.append(evidence_id)
        skill["evidence_ids"] = existing_evidence
        if not skill.get("category") and duplicate.get("category"):
            skill["category"] = _clean_text(duplicate.get("category"))
        return


@lru_cache(maxsize=1)
def _esco_index() -> EscoIndex:
    return EscoIndex.from_env()


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
