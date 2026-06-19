"""Person-job matching service orchestration."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.algorithms.pipeline import match_jd_resume


SCORE_KEYS = (
    "skill_coverage",
    "distribution_similarity",
    "experience_fit",
    "education_fit",
    "domain_fit",
    "semantic_fit",
)


def run_match(
    jd_text: str,
    resume_text: str,
    use_llm: bool = False,
    save_artifacts: bool = True,
) -> Dict[str, Any]:
    result = match_jd_resume(
        jd_text=jd_text,
        resume_text=resume_text,
        use_llm=use_llm,
        save_artifacts=save_artifacts,
    )
    match_result = result.get("match_result", {})
    partial_skills = list(match_result.get("insufficient_skills") or [])
    response = {
        "final_score": match_result.get("final_score", 0.0),
        "decision": match_result.get("decision", ""),
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
        "partial_skills": partial_skills,
        "score_detail": {key: match_result.get(key) for key in SCORE_KEYS},
        "explanation": match_result.get("explanation", ""),
        "graph": result.get("graph", {}),
        "jd_parse": result.get("jd_parse", {}),
        "resume_parse": result.get("resume_parse", {}),
        "match_result": match_result,
        "llm_used": bool(match_result.get("llm_used", False)),
        "llm_status": match_result.get("llm_status", {}),
    }
    return response
