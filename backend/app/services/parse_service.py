"""
Parse service orchestration for JD and resume inputs.
增强版：支持数据库持久化 + JSON文件备用存储
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from datetime import datetime

from backend.app.algorithms.pipeline import parse_jd, parse_resume
from backend.app.core.config import DB_AVAILABLE, settings
from backend.app.storage.json_store import save_json


def parse_jd_profile(text: str, use_llm: bool = False, db=None) -> Dict[str, Any]:
    """
    解析JD文本
    
    Args:
        text: JD原始文本
        use_llm: 是否使用LLM增强
        db: 数据库会话（可选，传入则保存到数据库）
    
    Returns:
        解析结果字典，包含job_profile、jd_parse等字段
    """
    # 1. 调用Demo原有算法（保持不变）
    result = parse_jd(text, use_llm=use_llm)
    
    # 2. 尝试保存到数据库
    if DB_AVAILABLE and db is not None:
        try:
            from backend.app.models.jd import Jd
            
            # 提取标题
            job_profile = result.get("job_profile", {})
            title = job_profile.get("title") or "未命名岗位"
            
            jd_record = Jd(
                title=title[:200],
                company=job_profile.get("company"),
                raw_content=text,
                structured_data=result.get("job_profile"),
                confidence=0.85,  # 默认置信度
            )
            db.add(jd_record)
            db.commit()
            db.refresh(jd_record)
            
            # 将数据库ID附加到结果中
            result["db_id"] = jd_record.id
            print(f"✓ JD已保存到数据库 (id={jd_record.id})")
            
        except Exception as e:
            print(f"⚠ 数据库保存失败，使用JSON备用: {e}")
            if db:
                db.rollback()
    
    # 3. 始终保存JSON文件（Demo原有逻辑）
    try:
        from backend.app.storage.paths import get_normalized_path
        filepath = get_normalized_path(f"jd_{text[:50]}", "jd")
        save_json(filepath, {
            **result,
            "parsed_at": datetime.now().isoformat(),
            "source": "api",
        })
    except Exception as e:
        print(f"⚠ JSON文件保存失败: {e}")
    
    return result


def parse_resume_profile(text: str, use_llm: bool = False, db=None) -> Dict[str, Any]:
    """
    解析简历文本
    
    Args:
        text: 简历原始文本
        use_llm: 是否使用LLM增强
        db: 数据库会话（可选）
    
    Returns:
        解析结果字典
    """
    # 1. 调用Demo原有算法
    result = parse_resume(text, use_llm=use_llm)
    
    # 2. 尝试保存到数据库
    if DB_AVAILABLE and db is not None:
        try:
            from backend.app.models.resume import Resume
            
            resume_profile = result.get("resume_profile", {})
            name = resume_profile.get("name") or "未知候选人"
            
            resume_record = Resume(
                name=name[:100],
                raw_content=text,
                structured_data=resume_profile,
                parse_status="completed",
                parse_confidence=0.88,
                parsed_at=datetime.now(),
            )
            db.add(resume_record)
            db.commit()
            db.refresh(resume_record)
            
            result["db_id"] = resume_record.id
            print(f"✓ 简历已保存到数据库 (id={resume_record.id})")
            
        except Exception as e:
            print(f"⚠ 数据库保存失败，使用JSON备用: {e}")
            if db:
                db.rollback()
    
    # 3. 保存JSON文件
    try:
        from backend.app.storage.paths import get_normalized_path
        filepath = get_normalized_path(f"resume_{text[:50]}", "resume")
        save_json(filepath, {
            **result,
            "parsed_at": datetime.now().isoformat(),
            "source": "api",
        })
    except Exception as e:
        print(f"⚠ JSON文件保存失败: {e}")
    
    return result
