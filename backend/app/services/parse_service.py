"""Parse service orchestration for JD and resume inputs."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.algorithms.pipeline import parse_jd, parse_resume


def parse_jd_profile(text: str, use_llm: bool = False) -> Dict[str, Any]:
    return parse_jd(text, use_llm=use_llm)


def parse_resume_profile(text: str, use_llm: bool = False) -> Dict[str, Any]:
    return parse_resume(text, use_llm=use_llm)
