"""Rule-based person-job matching score calculation."""

from __future__ import annotations

import abc
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.app.algorithms.common import MatchResult, ModelAdapterOutput, SkillProfile, clamp
from backend.app.algorithms.skill_extractor import _find_aliases
from backend.app.algorithms.skill_catalog import DEGREE_ORDER, JD_VERBS, RELATED_LOOKUP


class Matcher(abc.ABC):
    @abc.abstractmethod
    def match(
        self,
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        model_output: Optional[ModelAdapterOutput] = None,
        scoring_config: Optional[Dict[str, Any]] = None,
    ) -> MatchResult:
        raise NotImplementedError


class RuleBasedMatcher(Matcher):
    DEFAULT_SCORING_CONFIG = {
        "skill_coverage_weight": 0.50,
        "distribution_similarity_weight": 0.20,
        "experience_fit_weight": 0.10,
        "education_fit_weight": 0.08,
        "domain_fit_weight": 0.07,
        "semantic_fit_weight": 0.05,
    }

    def match(
        self,
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        model_output: Optional[ModelAdapterOutput] = None,
        scoring_config: Optional[Dict[str, Any]] = None,
    ) -> MatchResult:
        config = {**self.DEFAULT_SCORING_CONFIG, **(scoring_config or {})}
        job_skills = job_profile.skills
        resume_skill_map = {skill["name"]: skill for skill in resume_profile.skills}
        matched_skills: List[Dict[str, Any]] = []
        missing_skills: List[Dict[str, Any]] = []
        insufficient_skills: List[Dict[str, Any]] = []

        total_weight = sum(skill["weight"] for skill in job_skills)
        weighted_match = 0.0

        for job_skill in job_skills:
            match_info = self._match_skill(job_skill, resume_skill_map)
            weighted_match += job_skill["weight"] * match_info["match_score"]
            if match_info["match_score"] > 0:
                matched_skills.append(match_info["matched_item"])
            if match_info.get("insufficient_item"):
                insufficient_skills.append(match_info["insufficient_item"])
            if match_info["match_score"] == 0 and job_skill["requirement_level"] != "preferred":
                missing_skills.append(self._missing_item(job_skill))

        skill_coverage = weighted_match / total_weight if total_weight else 0.0
        distribution_similarity = cosine_similarity(job_profile.skill_distribution, resume_profile.skill_distribution)
        experience_fit = experience_fit_score(
            job_profile.metadata.get("experience_requirement"),
            resume_profile.metadata.get("experience_years", 0.0),
        )
        education_fit = education_fit_score(
            job_profile.metadata.get("education_requirement"),
            resume_profile.metadata.get("education"),
            resume_profile.metadata.get("experience_years", 0.0),
            job_profile.metadata.get("experience_requirement"),
            len(resume_profile.skills),
        )
        domain_fit = domain_fit_score(
            job_profile.metadata.get("domain_requirement", []),
            resume_profile.metadata.get("domain_experiences", []),
            skill_coverage,
        )
        semantic_fit = model_output.semantic_score if model_output else keyword_semantic_similarity(
            " ".join(skill["name"] for skill in job_profile.skills),
            " ".join(skill["name"] for skill in resume_profile.skills),
        )

        hard_penalties = self._hard_penalties(
            missing_skills=missing_skills,
            job_profile=job_profile,
            resume_profile=resume_profile,
            skill_coverage=skill_coverage,
            experience_fit=experience_fit,
            education_fit=education_fit,
        )
        penalty_value = sum(item["penalty"] for item in hard_penalties)
        score = 100 * (
            config["skill_coverage_weight"] * skill_coverage
            + config["distribution_similarity_weight"] * distribution_similarity
            + config["experience_fit_weight"] * experience_fit
            + config["education_fit_weight"] * education_fit
            + config["domain_fit_weight"] * domain_fit
            + config["semantic_fit_weight"] * semantic_fit
        ) - penalty_value
        final_score = round(clamp(score, 0, 100), 2)

        matched_skills.sort(key=lambda item: (-item["contribution"], item["name"]))
        missing_skills.sort(key=lambda item: (-item["jd_weight"], item["name"]))
        insufficient_skills.sort(key=lambda item: (-item["jd_weight"], item["name"]))

        explanation = build_match_explanation(final_score, matched_skills, missing_skills, insufficient_skills)
        return MatchResult(
            final_score=final_score,
            skill_coverage=round(skill_coverage, 3),
            distribution_similarity=round(distribution_similarity, 3),
            experience_fit=round(experience_fit, 3),
            education_fit=round(education_fit, 3),
            domain_fit=round(domain_fit, 3),
            semantic_fit=round(semantic_fit, 3),
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            insufficient_skills=insufficient_skills,
            hard_penalties=hard_penalties,
            explanation=explanation,
        )

    def _match_skill(self, job_skill: Dict[str, Any], resume_skill_map: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
        name = job_skill["name"]
        required_level = required_proficiency(job_skill)
        if name in resume_skill_map:
            resume_skill = resume_skill_map[name]
            proficiency = resume_skill["proficiency"]
            if proficiency >= required_level:
                match_score = 1.0
            elif proficiency >= max(0.0, required_level - 0.2):
                match_score = 0.7
            else:
                match_score = 0.5
            contribution = round(job_skill["weight"] * match_score, 3)
            matched_item = {
                "skill_id": job_skill["skill_id"],
                "name": name,
                "match_type": "exact",
                "jd_weight": job_skill["weight"],
                "resume_proficiency": proficiency,
                "contribution": contribution,
                "evidence_refs": {
                    "jd": job_skill.get("evidence_refs", []),
                    "resume": resume_skill.get("evidence_refs", []),
                },
                "evidence_from_jd": job_skill.get("evidence_texts", [])[:2],
                "evidence_from_resume": resume_skill.get("evidence_texts", [])[:2],
            }
            insufficient_item = None
            if proficiency < required_level:
                insufficient_item = {
                    "skill_id": job_skill["skill_id"],
                    "name": name,
                    "required_level": round(required_level, 3),
                    "resume_level": proficiency,
                    "jd_weight": job_skill["weight"],
                    "gap_type": "insufficient",
                    "evidence_refs": matched_item["evidence_refs"],
                }
            return {"match_score": match_score, "matched_item": matched_item, "insufficient_item": insufficient_item}

        related = best_related_skill(name, resume_skill_map)
        if related:
            related_skill, relation_type = related
            match_score = 0.5
            matched_item = {
                "skill_id": job_skill["skill_id"],
                "name": name,
                "match_type": "related",
                "related_resume_skill": related_skill["name"],
                "relation_type": relation_type,
                "jd_weight": job_skill["weight"],
                "resume_proficiency": related_skill["proficiency"],
                "contribution": round(job_skill["weight"] * match_score, 3),
                "evidence_refs": {
                    "jd": job_skill.get("evidence_refs", []),
                    "resume": related_skill.get("evidence_refs", []),
                },
                "evidence_from_jd": job_skill.get("evidence_texts", [])[:2],
                "evidence_from_resume": related_skill.get("evidence_texts", [])[:2],
            }
            insufficient_item = {
                "skill_id": job_skill["skill_id"],
                "name": name,
                "required_level": round(required_level, 3),
                "resume_level": related_skill["proficiency"],
                "jd_weight": job_skill["weight"],
                "gap_type": "related_only",
                "evidence_refs": matched_item["evidence_refs"],
            }
            return {"match_score": match_score, "matched_item": matched_item, "insufficient_item": insufficient_item}

        return {"match_score": 0.0, "matched_item": None, "insufficient_item": None}

    def _missing_item(self, job_skill: Dict[str, Any]) -> Dict[str, Any]:
        priority_value = job_skill["weight"] * (1.0 if job_skill["requirement_level"] == "required" else 0.6)
        if priority_value >= 1.0:
            priority = "high"
        elif priority_value >= 0.6:
            priority = "medium"
        else:
            priority = "low"
        return {
            "skill_id": job_skill["skill_id"],
            "name": job_skill["name"],
            "jd_weight": job_skill["weight"],
            "priority": priority,
            "gap_priority": round(priority_value, 3),
            "evidence_refs": {"jd": job_skill.get("evidence_refs", [])},
            "evidence_from_jd": job_skill.get("evidence_texts", [])[:2],
        }

    def _hard_penalties(
        self,
        missing_skills: Sequence[Dict[str, Any]],
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        skill_coverage: float,
        experience_fit: float,
        education_fit: float,
    ) -> List[Dict[str, Any]]:
        penalties: List[Dict[str, Any]] = []
        core_missing = [skill for skill in missing_skills if skill["jd_weight"] >= 0.9]
        if len(core_missing) >= 2:
            penalties.append({"reason": "核心必备技能缺失 2 个及以上", "penalty": 20})

        required_years = job_profile.metadata.get("experience_requirement")
        resume_years = resume_profile.metadata.get("experience_years") or 0.0
        if required_years is not None and required_years - resume_years > 2:
            penalties.append({"reason": "年限严重不足", "penalty": 15})

        if education_fit <= 0.3 and job_profile.metadata.get("education_requirement"):
            penalties.append({"reason": "学历硬门槛不满足", "penalty": 10})

        job_category = job_profile.metadata.get("job_category")
        target_position = resume_profile.metadata.get("target_position") or ""
        if target_position and job_category and skill_coverage < 0.25:
            if not any(keyword in target_position for keyword in job_category.replace("岗", "").split("/")):
                penalties.append({"reason": "岗位方向明显不一致", "penalty": 10})
        return penalties


def required_proficiency(job_skill: Mapping[str, Any]) -> float:
    weight = float(job_skill.get("weight", 0.6))
    if weight >= 1.2:
        return 0.8
    if weight >= 0.9:
        return 0.6
    if job_skill.get("requirement_level") == "preferred":
        return 0.4
    return 0.5


def best_related_skill(required_skill: str, resume_skill_map: Mapping[str, Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], str]]:
    candidates = []
    for related_name, relation_type in RELATED_LOOKUP.get(required_skill, []):
        if related_name in resume_skill_map:
            candidates.append((resume_skill_map[related_name], relation_type))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0].get("proficiency", 0.0))


def cosine_similarity(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    left_norm = math.sqrt(sum(left.get(key, 0.0) ** 2 for key in keys))
    right_norm = math.sqrt(sum(right.get(key, 0.0) ** 2 for key in keys))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return clamp(dot / (left_norm * right_norm))


def keyword_semantic_similarity(left_text: str, right_text: str) -> float:
    left_tokens = semantic_tokens(left_text)
    right_tokens = semantic_tokens(right_text)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    jaccard = len(overlap) / len(left_tokens | right_tokens)
    verb_overlap = len((left_tokens & set(JD_VERBS)) & right_tokens) / max(1, len(left_tokens & set(JD_VERBS)))
    return clamp(0.75 * jaccard + 0.25 * verb_overlap)


def semantic_tokens(text: str) -> set:
    tokens = set()
    for alias, standard, _offset in _find_aliases(text):
        tokens.add(standard)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[\u4e00-\u9fff]{2,}", text):
        if len(token) >= 2:
            tokens.add(token.lower())
    for verb in JD_VERBS:
        if verb in text:
            tokens.add(verb)
    return tokens


def experience_fit_score(required_years: Optional[float], resume_years: float) -> float:
    if required_years is None:
        return 0.8
    gap = required_years - resume_years
    if gap <= 0:
        return 1.0
    if gap <= 1:
        return 0.8
    if gap <= 2:
        return 0.5
    return 0.2


def education_fit_score(
    required_education: Optional[str],
    resume_education: Optional[str],
    resume_years: float,
    required_years: Optional[float],
    resume_skill_count: int,
) -> float:
    if not required_education:
        return 0.8
    if not resume_education:
        return 0.3
    required_rank = DEGREE_ORDER.get(required_education, 0)
    resume_rank = DEGREE_ORDER.get(resume_education, 0)
    if resume_rank >= required_rank:
        return 1.0
    strong_experience = resume_years >= (required_years or 0) + 2 or resume_skill_count >= 8
    if required_rank - resume_rank == 1 and strong_experience:
        return 0.7
    return 0.3


def domain_fit_score(required_domains: Sequence[str], resume_domains: Sequence[str], skill_coverage: float) -> float:
    if not required_domains:
        return 0.8
    required = set(required_domains)
    resume = set(resume_domains)
    if required & resume:
        return 1.0
    related_pairs = {
        ("电商", "用户增长"),
        ("电商", "供应链"),
        ("金融", "风控"),
        ("企业服务", "SaaS"),
        ("招聘业务", "企业服务"),
        ("内容推荐", "电商"),
        ("知识库问答", "企业服务"),
    }
    if any((left in required and right in resume) or (right in required and left in resume) for left, right in related_pairs):
        return 0.7
    if skill_coverage >= 0.45:
        return 0.4
    return 0.2


def build_match_explanation(
    final_score: float,
    matched_skills: Sequence[Dict[str, Any]],
    missing_skills: Sequence[Dict[str, Any]],
    insufficient_skills: Sequence[Dict[str, Any]],
) -> str:
    matched_names = [skill["name"] for skill in matched_skills[:4]]
    missing_names = [skill["name"] for skill in missing_skills[:4]]
    insufficient_names = [skill["name"] for skill in insufficient_skills[:3]]
    matched_text = "、".join(matched_names) if matched_names else "暂无核心技能"
    missing_text = "、".join(missing_names) if missing_names else "无明显核心缺口"
    insufficient_text = "、".join(insufficient_names) if insufficient_names else ""

    if final_score >= 75:
        return f"候选人与岗位在 {matched_text} 等核心技能上匹配度较高，项目或工作经历中存在可解释证据；主要缺口为 {missing_text}。"
    if final_score >= 55:
        suffix = f"，其中 {insufficient_text} 的证据仍需加强" if insufficient_text else ""
        return f"候选人具备部分核心技能，如 {matched_text}{suffix}；但在 {missing_text} 等岗位重点能力上证据不足，因此整体匹配度中等。"
    return f"岗位要求集中在 {missing_text} 等能力，简历当前只体现 {matched_text}，核心技能覆盖不足，因此匹配度偏低。"
