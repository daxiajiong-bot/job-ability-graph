from __future__ import annotations

from backend.schemas import JDRecord, MatchResult, ResumeRecord
from backend.skill_normalizer import normalize_skills


def _skill_set(values):
    return set(normalize_skills(values))


def match_resume_to_jd(resume: ResumeRecord, jd: JDRecord) -> MatchResult:
    resume_skills = _skill_set(resume.skills)
    jd_skills = _skill_set(jd.skills_norm or jd.skills_raw)
    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)
    total = len(jd_skills) or 1
    score = round(len(matched) / total * 100, 1)
    return MatchResult(
        match_score=score,
        matched_skills=matched,
        missing_skills=missing,
        explanation=f"已匹配 {len(matched)} 项技能，缺少 {len(missing)} 项技能。",
    )
