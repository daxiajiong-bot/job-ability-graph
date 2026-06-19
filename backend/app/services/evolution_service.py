"""Evolution service for emerging jobs and position update analysis."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from backend.app.algorithms.job_intelligence import compare_job_versions, discover_emerging_job
from backend.app.llm.evolution_explainer import explain_new_position, explain_position_update


def discover_position(source_documents: Sequence[Dict[str, Any]], use_llm: bool = False) -> Dict[str, Any]:
    result = discover_emerging_job(source_documents)
    result["llm"] = explain_new_position(list(source_documents)) if use_llm else {
        "llm_used": False,
        "message": "LLM was not requested. Using rule-based pipeline.",
        "source": "rule_based",
    }
    return result


def update_position(old_jd_text: str, new_jd_text: str, use_llm: bool = False) -> Dict[str, Any]:
    result = compare_job_versions(old_jd_text=old_jd_text, new_jd_text=new_jd_text)
    result["llm"] = explain_position_update(result.get("old_job_profile", {}), result.get("new_job_profile", {})) if use_llm else {
        "llm_used": False,
        "message": "LLM was not requested. Using rule-based pipeline.",
        "source": "rule_based",
    }
    return result
