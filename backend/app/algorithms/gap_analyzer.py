"""Ability gap analysis for matched job and resume profiles."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from backend.app.algorithms.common import GapAnalysisResult, MatchResult, SkillProfile


class GapAnalyzer:
    def analyze(self, job_profile: SkillProfile, resume_profile: SkillProfile, match_result: MatchResult) -> GapAnalysisResult:
        missing = []
        for skill in match_result.missing_skills:
            priority = skill["priority"]
            missing.append(
                {
                    "skill_id": skill["skill_id"],
                    "name": skill["name"],
                    "priority": priority,
                    "reason": f"JD 中权重为 {skill['jd_weight']}，简历未提供直接或相关证据。",
                    "jd_evidence_refs": skill.get("evidence_refs", {}).get("jd", []),
                }
            )

        insufficient = []
        for skill in match_result.insufficient_skills:
            insufficient.append(
                {
                    "skill_id": skill["skill_id"],
                    "name": skill["name"],
                    "required_level": skill["required_level"],
                    "current_level": skill["resume_level"],
                    "reason": "简历有相关证据，但熟练度或技能关系不足以完全满足岗位要求。",
                    "resume_evidence_refs": skill.get("evidence_refs", {}).get("resume", []),
                }
            )

        related_only = []
        for skill in match_result.matched_skills:
            if skill.get("match_type") == "related":
                related_only.append(
                    {
                        "required_skill_id": skill["skill_id"],
                        "required_skill_name": skill["name"],
                        "resume_related_skill": skill.get("related_resume_skill"),
                        "relation_type": skill.get("relation_type", "related"),
                        "reason": "简历具备相关技能，但缺少 JD 技能的直接证据。",
                    }
                )

        suggestions = []
        for skill in missing[:5]:
            suggestions.append(
                {
                    "skill_id": skill["skill_id"],
                    "suggestion": f"补充 {skill['name']} 的学习、项目或工作证据，优先覆盖 JD 中的核心场景。",
                    "priority": skill["priority"],
                }
            )
        for skill in insufficient[:3]:
            suggestions.append(
                {
                    "skill_id": skill["skill_id"],
                    "suggestion": f"强化 {skill['name']} 的项目深度描述，例如职责、产出、指标或上线结果。",
                    "priority": "medium",
                }
            )

        gap_summary = build_gap_summary(missing, insufficient, related_only)
        return GapAnalysisResult(
            missing_skills=missing,
            insufficient_skills=insufficient,
            related_only_skills=related_only,
            improvement_suggestions=suggestions,
            gap_summary=gap_summary,
        )


def build_gap_summary(
    missing: Sequence[Dict[str, Any]],
    insufficient: Sequence[Dict[str, Any]],
    related_only: Sequence[Dict[str, Any]],
) -> str:
    parts = []
    if missing:
        parts.append(f"缺失 {len(missing)} 项技能，优先补齐 {', '.join(item['name'] for item in missing[:3])}")
    if insufficient:
        parts.append(f"{len(insufficient)} 项技能证据或熟练度不足")
    if related_only:
        parts.append(f"{len(related_only)} 项技能仅存在相关能力支撑")
    return "；".join(parts) if parts else "未发现明显能力差距"
