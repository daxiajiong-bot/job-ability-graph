"""LLM-reserved JD extraction helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.llm.client import call_llm, is_llm_available
from backend.app.llm.prompts import JD_EXTRACTION_PROMPT


def extract_jd_with_llm(text: str) -> Dict[str, Any]:
    availability = is_llm_available()
    if not availability["available"]:
        return {"llm_used": False, **availability}
    return call_llm(JD_EXTRACTION_PROMPT.replace("{jd_text}", text), json_mode=True)


def merge_jd_profiles(rule_profile: Dict[str, Any], llm_profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(rule_profile)
    llm_profile = llm_profile or {}
    merged["llm_used"] = bool(llm_profile.get("llm_used"))
    merged["llm_status"] = {
        "available": bool(llm_profile.get("available", False)),
        "message": llm_profile.get("message", "LLM was not requested."),
    }
    merged["llm_profile"] = llm_profile.get("data")
    return merged
