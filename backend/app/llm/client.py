"""Safe placeholder LLM client.

This demo intentionally does not connect to any real LLM provider. The client
keeps the integration point explicit while making the rule-based pipeline the
only executable path by default.
"""

from __future__ import annotations

from typing import Any, Dict


LLM_NOT_CONFIGURED_MESSAGE = "LLM is not configured. Using rule-based pipeline."


def is_llm_available() -> Dict[str, Any]:
    return {"available": False, "message": LLM_NOT_CONFIGURED_MESSAGE}


def call_llm(prompt: str, json_mode: bool = True) -> Dict[str, Any]:
    return {
        "available": False,
        "llm_used": False,
        "json_mode": json_mode,
        "message": LLM_NOT_CONFIGURED_MESSAGE,
        "prompt_preview": prompt[:240],
        "data": None,
    }
