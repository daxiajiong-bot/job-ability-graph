"""LLM-reserved person-job match explanation helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, Sequence

from backend.app.llm.client import call_llm, is_llm_available
from backend.app.llm.prompts import MATCH_EXPLANATION_PROMPT


def explain_match_with_llm(
    jd_profile: Dict[str, Any],
    resume_profile: Dict[str, Any],
    match_result: Dict[str, Any],
    evidence_items: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    availability = is_llm_available()
    fallback = _rule_based_explanation(match_result)
    if not availability["available"]:
        return {
            "llm_used": False,
            **availability,
            "explanation": fallback,
            "source": "rule_based_fallback",
        }
    prompt = (
        MATCH_EXPLANATION_PROMPT.replace("{jd_profile}", json.dumps(jd_profile, ensure_ascii=False))
        .replace("{resume_profile}", json.dumps(resume_profile, ensure_ascii=False))
        .replace("{match_result}", json.dumps(match_result, ensure_ascii=False))
        .replace("{evidence_items}", json.dumps(list(evidence_items), ensure_ascii=False))
    )
    response = call_llm(prompt, json_mode=True)
    if not response.get("llm_used"):
        response["explanation"] = fallback
        response["source"] = "rule_based_fallback"
    return response


def _rule_based_explanation(match_result: Dict[str, Any]) -> str:
    final_score = float(match_result.get("final_score", 0.0))
    matched = "、".join(item.get("name", "") for item in match_result.get("matched_skills", [])[:3]) or "暂无核心技能"
    missing = "、".join(item.get("name", "") for item in match_result.get("missing_skills", [])[:3]) or "无明显核心缺口"
    if final_score >= 75:
        return f"规则结果显示候选人在 {matched} 等技能上匹配较好，主要缺口为 {missing}。"
    if final_score >= 55:
        return f"规则结果显示候选人具备 {matched} 等部分能力，但 {missing} 等方面仍需加强。"
    return f"规则结果显示候选人与岗位匹配偏低，当前主要命中 {matched}，缺口集中在 {missing}。"
