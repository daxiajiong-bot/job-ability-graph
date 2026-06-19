"""Replaceable model adapter layer for semantic matching features."""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Sequence

from backend.app.algorithms.common import ModelAdapterOutput, SkillProfile
from backend.app.algorithms.matcher import best_related_skill, keyword_semantic_similarity


class ModelAdapter(abc.ABC):
    """Replaceable model layer for semantic features."""

    @abc.abstractmethod
    def predict(
        self,
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        jd_evidence_items: Sequence[Dict[str, Any]],
        resume_evidence_items: Sequence[Dict[str, Any]],
        runtime_options: Optional[Dict[str, Any]] = None,
    ) -> ModelAdapterOutput:
        raise NotImplementedError


class RuleModelAdapter(ModelAdapter):
    """Rule-only adapter used by the first-stage demo."""

    def predict(
        self,
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        jd_evidence_items: Sequence[Dict[str, Any]],
        resume_evidence_items: Sequence[Dict[str, Any]],
        runtime_options: Optional[Dict[str, Any]] = None,
    ) -> ModelAdapterOutput:
        jd_text = " ".join(item["text"] for item in jd_evidence_items if item.get("section") == "responsibilities")
        resume_text = " ".join(item["text"] for item in resume_evidence_items if item.get("section") in {"work_experiences", "projects"})
        semantic_score = keyword_semantic_similarity(jd_text, resume_text)

        job_skills = {skill["name"]: skill for skill in job_profile.skills}
        resume_skills = {skill["name"]: skill for skill in resume_profile.skills}
        contributions = []
        for name, skill in job_skills.items():
            if name in resume_skills:
                contribution = skill["weight"] * resume_skills[name]["proficiency"]
            else:
                related = best_related_skill(name, resume_skills)
                contribution = skill["weight"] * 0.35 if related else 0.0
            contributions.append(
                {
                    "skill_id": skill["skill_id"],
                    "name": name,
                    "contribution_score": round(contribution, 3),
                    "evidence_refs": skill.get("evidence_refs", []),
                }
            )

        item_weights = []
        for evidence in jd_evidence_items:
            text_score = keyword_semantic_similarity(evidence["text"], resume_text)
            item_weights.append({"evidence_id": evidence["evidence_id"], "weight": round(text_score, 3)})

        return ModelAdapterOutput(
            semantic_score=round(semantic_score, 3),
            job_embedding=None,
            resume_embedding=None,
            skill_contributions=sorted(contributions, key=lambda item: item["contribution_score"], reverse=True),
            item_weights=item_weights,
            model_explanation="规则适配器基于职责/经历关键词重合与技能上下文计算语义分。",
            model_metadata={"model_name": "rule", "version": "demo-v1", "uses_jobformer": False},
        )
