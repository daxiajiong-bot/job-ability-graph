"""Competition-oriented job intelligence utilities.

This module keeps emerging-job discovery and existing-job update analysis
separate from JD/resume matching. The current implementation is rule based and
uses JD skill profiles as the shared contract, so it can later be replaced by
multi-source clustering, time-series mining, or a JobFormer-backed model layer.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.app.algorithms.pipeline import parse_jd


@dataclasses.dataclass
class SourceDocument:
    text: str
    source_id: Optional[str] = None
    source_type: str = "jd"
    collected_at: Optional[str] = None
    reliability: float = 0.8


def _source_to_dict(source: SourceDocument) -> Dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "collected_at": source.collected_at,
        "reliability": source.reliability,
    }


def _skill_map(profile: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {skill["name"]: skill for skill in profile.get("skills", [])}


def _skill_evidence(skill: Mapping[str, Any]) -> List[str]:
    return list(skill.get("evidence_texts") or [])[:3]


def _top_skills(skills: Iterable[Mapping[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for skill in skills:
        bucket = grouped.setdefault(
            skill["name"],
            {
                "skill_id": skill["skill_id"],
                "name": skill["name"],
                "skill_type": skill["skill_type"],
                "max_weight": 0.0,
                "support_count": 0,
                "evidence": [],
            },
        )
        bucket["max_weight"] = max(bucket["max_weight"], float(skill.get("weight", 0.0)))
        bucket["support_count"] += int(skill.get("support_count", 1))
        bucket["evidence"].extend(_skill_evidence(skill))

    ranked = []
    for item in grouped.values():
        item["score"] = round(item["max_weight"] * (1 + 0.15 * (item["support_count"] - 1)), 3)
        item["evidence"] = sorted(set(item["evidence"]))[:3]
        ranked.append(item)
    ranked.sort(key=lambda item: (-item["score"], -item["support_count"], item["name"]))
    return ranked[:limit]


def compare_job_versions(old_jd_text: str, new_jd_text: str) -> Dict[str, Any]:
    """Compare two JD versions and report added/removed/modified skill needs."""
    old_result = parse_jd(old_jd_text)
    new_result = parse_jd(new_jd_text)
    old_profile = old_result["job_profile"]
    new_profile = new_result["job_profile"]
    old_skills = _skill_map(old_profile)
    new_skills = _skill_map(new_profile)

    added = []
    for name in sorted(set(new_skills) - set(old_skills)):
        skill = new_skills[name]
        added.append(
            {
                "skill_id": skill["skill_id"],
                "name": name,
                "skill_type": skill["skill_type"],
                "new_weight": skill["weight"],
                "evidence": _skill_evidence(skill),
            }
        )

    removed = []
    for name in sorted(set(old_skills) - set(new_skills)):
        skill = old_skills[name]
        removed.append(
            {
                "skill_id": skill["skill_id"],
                "name": name,
                "skill_type": skill["skill_type"],
                "old_weight": skill["weight"],
                "evidence": _skill_evidence(skill),
            }
        )

    modified = []
    for name in sorted(set(old_skills) & set(new_skills)):
        old_skill = old_skills[name]
        new_skill = new_skills[name]
        delta = round(float(new_skill["weight"]) - float(old_skill["weight"]), 3)
        level_changed = old_skill.get("requirement_level") != new_skill.get("requirement_level")
        if abs(delta) >= 0.15 or level_changed:
            modified.append(
                {
                    "skill_id": new_skill["skill_id"],
                    "name": name,
                    "skill_type": new_skill["skill_type"],
                    "old_weight": old_skill["weight"],
                    "new_weight": new_skill["weight"],
                    "weight_delta": delta,
                    "old_level": old_skill.get("requirement_level"),
                    "new_level": new_skill.get("requirement_level"),
                    "new_evidence": _skill_evidence(new_skill),
                }
            )

    added.sort(key=lambda item: (-item["new_weight"], item["name"]))
    removed.sort(key=lambda item: (-item["old_weight"], item["name"]))
    modified.sort(key=lambda item: (-abs(item["weight_delta"]), item["name"]))

    update_summary = _build_update_summary(added, removed, modified)
    return {
        "mode": "job_update_analysis",
        "old_jd": old_result["jd_parse"],
        "new_jd": new_result["jd_parse"],
        "old_job_profile": old_profile,
        "new_job_profile": new_profile,
        "ability_changes": {
            "added_skills": added,
            "removed_skills": removed,
            "modified_skills": modified,
        },
        "update_summary": update_summary,
        "competition_hooks": {
            "supports_existing_job_ability_update": True,
            "supports_manual_review": True,
            "supports_evidence_trace": True,
            "next_stage_required": ["time_series_sources", "enterprise_review_workflow", "change_reason_classifier"],
        },
    }


def discover_emerging_job(source_documents: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate multiple JD-like texts into a draft emerging job definition."""
    sources = [
        SourceDocument(
            text=str(item.get("text", "")).strip(),
            source_id=item.get("source_id") or item.get("id"),
            source_type=item.get("source_type", "jd"),
            collected_at=item.get("collected_at"),
            reliability=float(item.get("reliability", 0.8)),
        )
        for item in source_documents
        if str(item.get("text", "")).strip()
    ]
    if not sources:
        raise ValueError("source_documents must contain at least one non-empty text")

    parsed = []
    title_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    responsibility_counter: Counter[str] = Counter()
    skill_support: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for source in sources:
        result = parse_jd(source.text)
        jd_parse = result["jd_parse"]
        profile = result["job_profile"]
        parsed.append({"source": _source_to_dict(source), "jd_parse": jd_parse, "job_profile": profile})
        if jd_parse.get("job_title") and jd_parse["job_title"] != "未识别岗位":
            title_counter[jd_parse["job_title"]] += 1
        if jd_parse.get("job_category"):
            category_counter[jd_parse["job_category"]] += 1
        for domain in jd_parse.get("domain_requirement", []):
            domain_counter[domain] += 1
        for responsibility in jd_parse.get("responsibilities", []):
            responsibility_counter[responsibility] += 1
        for skill in profile.get("skills", []):
            enriched = {**skill, "source_id": source.source_id, "source_reliability": source.reliability}
            skill_support[skill["name"]].append(enriched)

    all_supported_skills = []
    for name, skill_items in skill_support.items():
        base = max(skill_items, key=lambda item: item.get("weight", 0.0))
        support_count = len({item.get("source_id") or index for index, item in enumerate(skill_items)})
        avg_reliability = sum(float(item.get("source_reliability", 0.8)) for item in skill_items) / len(skill_items)
        all_supported_skills.append(
            {
                **base,
                "support_count": support_count,
                "source_confidence": round(avg_reliability, 3),
                "cross_source_score": round(float(base.get("weight", 0.0)) * support_count * avg_reliability, 3),
            }
        )

    core_skills = _top_skills(
        [skill for skill in all_supported_skills if skill.get("requirement_level") != "preferred"],
        limit=10,
    )
    preferred_skills = _top_skills(
        [skill for skill in all_supported_skills if skill.get("requirement_level") == "preferred"],
        limit=8,
    )

    title = _draft_title(title_counter, core_skills)
    definition = {
        "job_title": title,
        "job_category": category_counter.most_common(1)[0][0] if category_counter else "新一代信息技术岗位",
        "core_responsibilities": [item for item, _count in responsibility_counter.most_common(6)],
        "required_skills": core_skills,
        "preferred_skills": preferred_skills,
        "typical_industry_scenarios": [item for item, _count in domain_counter.most_common(6)],
        "source_count": len(sources),
        "confidence": _discovery_confidence(len(sources), core_skills),
    }

    return {
        "mode": "emerging_job_discovery",
        "draft_job_definition": definition,
        "source_evidence": parsed,
        "cross_validation": {
            "skill_support_threshold": "support_count and source_confidence are exposed for manual review",
            "noise_control": "skills supported by multiple sources rank higher than one-off mentions",
            "hallucination_control": "all draft skills come from parsed source evidence",
        },
        "competition_hooks": {
            "supports_emerging_job_discovery": True,
            "supports_job_definition_generation": True,
            "supports_evidence_trace": True,
            "supports_manual_review": True,
            "next_stage_required": ["real_multi_source_crawling", "deduplication", "trend_detection"],
        },
    }


def _build_update_summary(
    added: Sequence[Mapping[str, Any]],
    removed: Sequence[Mapping[str, Any]],
    modified: Sequence[Mapping[str, Any]],
) -> str:
    parts = []
    if added:
        parts.append("新增能力: " + "、".join(item["name"] for item in added[:5]))
    if removed:
        parts.append("弱化/删除能力: " + "、".join(item["name"] for item in removed[:5]))
    if modified:
        parts.append("权重变化能力: " + "、".join(item["name"] for item in modified[:5]))
    return "；".join(parts) if parts else "两版 JD 未发现明显能力项变化"


def _draft_title(title_counter: Counter[str], core_skills: Sequence[Mapping[str, Any]]) -> str:
    if title_counter:
        return title_counter.most_common(1)[0][0]
    names = {skill["name"] for skill in core_skills[:5]}
    if "大语言模型" in names or "RAG" in names:
        return "大模型应用工程师"
    if "推荐算法" in names:
        return "推荐算法工程师"
    if "数据仓库" in names or "ETL" in names:
        return "数据开发工程师"
    return "新兴技术岗位"


def _discovery_confidence(source_count: int, core_skills: Sequence[Mapping[str, Any]]) -> float:
    if not core_skills:
        return 0.2
    support = sum(float(skill.get("support_count", 1)) for skill in core_skills[:5]) / max(1, len(core_skills[:5]))
    source_factor = min(1.0, source_count / 5)
    support_factor = min(1.0, support / max(1, source_count))
    return round(0.4 + 0.3 * source_factor + 0.3 * support_factor, 3)
