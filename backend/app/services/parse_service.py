"""Parse service orchestration for JD and resume inputs."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.algorithms.pipeline import parse_jd, parse_resume


def parse_jd_profile(text: str, use_llm: bool = False, save_artifacts: bool = True) -> Dict[str, Any]:
    """
    解析JD文本

    Args:
        text: JD原始文本
        use_llm: 是否使用LLM增强
        save_artifacts: 是否保存中间产物（默认True）
    """
    return parse_jd(text, use_llm=use_llm)


def parse_resume_profile(text: str, use_llm: bool = False, save_artifacts: bool = True) -> Dict[str, Any]:
    """
    解析简历文本

    Args:
        text: 简历原始文本
        use_llm: 是否使用LLM增强
        save_artifacts: 是否保存中间产物（默认True）
    """
    return parse_resume(text, use_llm=use_llm)
