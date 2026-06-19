"""
Person-job matching service orchestration.
增强版：支持数据库持久化 + 匹配历史记录
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from datetime import datetime

from backend.app.algorithms.pipeline import match_jd_resume
from backend.app.core.config import DB_AVAILABLE
from backend.app.storage.json_store import save_json


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
    position_id: Optional[int] = None,
    db=None,
) -> Dict[str, Any]:
    """
    执行人岗匹配
    
    Args:
        jd_text: JD文本
        resume_text: 简历文本
        use_llm: 是否使用LLM
        save_artifacts: 是否保存中间产物
        position_id: 关联的岗位ID（可选）
        db: 数据库会话（可选）
    
    Returns:
        匹配结果字典
    """
    # 1. 调用Demo原有算法（保持不变）
    result = match_jd_resume(
        jd_text=jd_text,
        resume_text=resume_text,
        use_llm=use_llm,
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
    
    # 2. 尝试保存匹配结果到数据库
    if DB_AVAILABLE and db is not None and position_id:
        try:
            from backend.app.models.matching_result import MatchingResult
            
            matching_record = MatchingResult(
                position_id=position_id,
                match_mode="jd_vs_resume",
                match_score=response["final_score"],
                match_reason=response["explanation"][:500] if response["explanation"] else None,
                gap_analysis={
                    "missing_skills": response["missing_skills"],
                    "partial_skills": response["partial_skills"],
                    "matched_skills": response["matched_skills"],
                },
                dimension_scores=response["score_detail"],
                recommended_skills=response.get("recommended_skills", []),
                learning_path=result.get("learning_path", {}),
            )
            db.add(matching_record)
            db.commit()
            db.refresh(matching_record)
            
            response["matching_record_id"] = matching_record.id
            print(f"✓ 匹配结果已保存到数据库 (id={matching_record.id}, score={response['final_score']})")
            
        except Exception as e:
            print(f"⚠ 匹配结果数据库保存失败: {e}")
            if db:
                db.rollback()
    
    # 3. 保存JSON文件（Demo原有逻辑）
    if save_artifacts:
        try:
            from backend.app.storage.paths import get_match_path
            filepath = get_match_path(jd_text, resume_text)
            save_json(filepath, {
                **response,
                "matched_at": datetime.now().isoformat(),
                "source": "api",
            })
        except Exception as e:
            print(f"⚠ 匹配结果JSON保存失败: {e}")
    
    return response
