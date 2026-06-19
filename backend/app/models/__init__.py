"""
数据库模型包 - 从JD_py迁移
包含：岗位、技能、JD、简历、匹配结果等核心模型
"""
from backend.app.core.config import Base

# 核心业务模型
from .position import Position
from .skill import Skill
from .jd import Jd
from .resume import Resume
from .matching_result import MatchingResult
from .position_skill_relation import PositionSkillRelation

__all__ = [
    "Position",
    "Skill", 
    "Jd",
    "Resume",
    "MatchingResult",
    "PositionSkillRelation",
]
