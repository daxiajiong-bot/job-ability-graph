"""LLM-reserved explanations for emerging jobs and position updates."""

from __future__ import annotations

import json
from typing import Any, Dict, Sequence

from backend.app.llm.client import call_llm, is_llm_available
from backend.app.llm.prompts import EMERGING_POSITION_PROMPT, POSITION_UPDATE_PROMPT


def explain_new_position(job_documents: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    availability = is_llm_available()
    if not availability["available"]:
        return {
            "llm_used": False,
            **availability,
            "explanation": "LLM 未配置，当前新岗位发现说明由规则聚合结果生成。",
            "source": "rule_based_mock",
        }
    return call_llm(EMERGING_POSITION_PROMPT.replace("{job_documents}", json.dumps(list(job_documents), ensure_ascii=False)), json_mode=True)


def explain_position_update(old_profile: Dict[str, Any], new_profile: Dict[str, Any]) -> Dict[str, Any]:
    availability = is_llm_available()
    if not availability["available"]:
        return {
            "llm_used": False,
            **availability,
            "explanation": "LLM 未配置，当前岗位能力更新说明由规则差异结果生成。",
            "source": "rule_based_mock",
        }
    prompt = (
        POSITION_UPDATE_PROMPT.replace("{old_profile}", json.dumps(old_profile, ensure_ascii=False))
        .replace("{new_profile}", json.dumps(new_profile, ensure_ascii=False))
    )
    return call_llm(prompt, json_mode=True)
