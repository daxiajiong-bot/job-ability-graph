"""Build reusable job and resume skill profiles from parsed inputs."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Sequence

from backend.app.algorithms.common import JDParseResult, NormalizedSkill, ResumeParseResult, SkillMention, SkillProfile, clamp
from backend.app.algorithms.skill_catalog import SKILL_CATALOG


class SkillProfileBuilder:
    JOB_SECTION_BASE_WEIGHT = {
        "requirements": 1.0,
        "responsibilities": 0.8,
        "job_title": 0.9,
        "preferred": 0.4,
    }

    def build_job_profile(self, jd_parse: JDParseResult, normalized_skills: Sequence[NormalizedSkill]) -> SkillProfile:
        mention_by_id = {mention.mention_id: mention for mention in jd_parse.raw_skill_mentions}
        skills: List[Dict[str, Any]] = []
        distribution: Dict[str, float] = {}

        for normalized in normalized_skills:
            mentions = [mention_by_id[ref] for ref in normalized.evidence_refs if ref in mention_by_id]
            if not mentions:
                continue
            section_weights = [self.JOB_SECTION_BASE_WEIGHT.get(mention.source_section, 0.6) for mention in mentions]
            base_weight = max(section_weights) if section_weights else 0.6
            evidence_text = " ".join(mention.evidence_text for mention in mentions)
            intensity_bonus = self._jd_intensity_bonus(evidence_text)
            if SKILL_CATALOG[normalized.name]["skill_type"] == "通用能力":
                base_weight = min(base_weight, 0.3)
            frequency_bonus = min(0.3, max(0, len(mentions) - 1) * 0.1)
            weight = round(min(1.5, base_weight + intensity_bonus + frequency_bonus), 3)
            requirement_level = self._requirement_level(mentions, weight)
            skill_item = {
                "skill_id": normalized.skill_id,
                "name": normalized.name,
                "skill_type": normalized.skill_type,
                "weight": weight,
                "requirement_level": requirement_level,
                "confidence": normalized.confidence,
                "aliases": normalized.aliases,
                "evidence_refs": normalized.evidence_refs,
                "evidence_texts": sorted({mention.evidence_text for mention in mentions}),
                "source_sections": sorted({mention.source_section for mention in mentions}),
            }
            skills.append(skill_item)
            distribution[normalized.name] = weight

        skills.sort(key=lambda item: (-item["weight"], item["name"]))
        vector = [distribution[name] for name in sorted(distribution)]
        return SkillProfile(
            profile_id="job:primary",
            profile_type="job",
            skills=skills,
            skill_distribution=distribution,
            vector=vector,
            metadata={
                "job_title": jd_parse.job_title,
                "job_category": jd_parse.job_category,
                "education_requirement": jd_parse.education_requirement,
                "experience_requirement": jd_parse.experience_requirement,
                "domain_requirement": jd_parse.domain_requirement,
            },
        )

    def build_resume_profile(self, resume_parse: ResumeParseResult, normalized_skills: Sequence[NormalizedSkill]) -> SkillProfile:
        mention_by_id = {mention.mention_id: mention for mention in resume_parse.raw_skill_mentions}
        skills: List[Dict[str, Any]] = []
        distribution: Dict[str, float] = {}

        for normalized in normalized_skills:
            mentions = [mention_by_id[ref] for ref in normalized.evidence_refs if ref in mention_by_id]
            if not mentions:
                continue
            scored_mentions = [self._resume_skill_score(mention) for mention in mentions]
            best_score = max(scored_mentions)
            confidence = round(max(mention.confidence for mention in mentions), 3)
            recency = round(max(self._recency_score(mention.evidence_text) for mention in mentions), 3)
            skill_item = {
                "skill_id": normalized.skill_id,
                "name": normalized.name,
                "skill_type": normalized.skill_type,
                "proficiency": round(best_score, 3),
                "confidence": confidence,
                "recency": recency,
                "aliases": normalized.aliases,
                "evidence_refs": normalized.evidence_refs,
                "evidence_texts": sorted({mention.evidence_text for mention in mentions}),
                "source_sections": sorted({mention.source_section for mention in mentions}),
            }
            skills.append(skill_item)
            distribution[normalized.name] = round(best_score * confidence, 3)

        skills.sort(key=lambda item: (-item["proficiency"], item["name"]))
        vector = [distribution[name] for name in sorted(distribution)]
        return SkillProfile(
            profile_id="resume:primary",
            profile_type="resume",
            skills=skills,
            skill_distribution=distribution,
            vector=vector,
            metadata={
                "candidate_id": resume_parse.candidate_id,
                "education": resume_parse.education,
                "experience_years": resume_parse.experience_years,
                "target_position": resume_parse.target_position,
                "domain_experiences": resume_parse.domain_experiences,
            },
        )

    def _jd_intensity_bonus(self, text: str) -> float:
        lowered = text.lower()
        bonus = 0.0
        if any(word in lowered for word in ("精通", "深入掌握", "专家级")):
            bonus += 0.3
        elif any(word in lowered for word in ("熟练", "熟悉", "具备", "经验")):
            bonus += 0.2
        if any(word in lowered for word in ("了解", "接触过")):
            bonus -= 0.2
        if any(word in lowered for word in ("优先", "加分", "preferred", "bonus")):
            bonus -= 0.4
        return bonus

    def _requirement_level(self, mentions: Sequence[SkillMention], weight: float) -> str:
        sections = {mention.source_section for mention in mentions}
        evidence_text = " ".join(mention.evidence_text for mention in mentions).lower()
        if "preferred" in sections or any(word in evidence_text for word in ("优先", "加分", "preferred", "bonus")):
            return "preferred"
        if weight >= 0.8 or sections & {"requirements", "responsibilities", "job_title"}:
            return "required"
        return "implicit"

    def _resume_skill_score(self, mention: SkillMention) -> float:
        text = mention.evidence_text
        if any(word in text for word in ("精通", "主导", "架构", "负责人", "Owner")):
            base = 1.0
        elif any(word in text for word in ("熟练", "独立完成", "核心开发", "核心负责", "落地", "优化")):
            base = 0.8
        elif any(word in text for word in ("熟悉", "参与开发", "参与", "具备经验", "使用", "开发", "实现", "负责")):
            base = 0.6
        elif any(word in text for word in ("了解", "接触", "学习过")):
            base = 0.3
        else:
            base = 0.55

        source_bonus = {
            "work_experiences": 0.2,
            "projects": 0.15,
            "skills": -0.1,
            "certificates": 0.1,
        }.get(mention.source_section, 0.0)
        recency_bonus = self._recency_bonus(text)
        return clamp(base + source_bonus + recency_bonus)

    def _recency_score(self, text: str) -> float:
        current_year = dt.date.today().year
        years = [int(year) for year in re.findall(r"(?:19|20)\d{2}", text)]
        if not years:
            return 0.8
        newest = max(years)
        gap = current_year - newest
        if gap <= 1:
            return 1.0
        if gap <= 3:
            return 0.8
        return 0.5

    def _recency_bonus(self, text: str) -> float:
        score = self._recency_score(text)
        if score >= 1.0:
            return 0.1
        if score >= 0.8:
            return 0.0
        return -0.1
