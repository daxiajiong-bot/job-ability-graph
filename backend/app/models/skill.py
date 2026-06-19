"""
数据库模型 - 技能表 (从JD_py迁移)
需求覆盖：全景图谱（技能级别/别名）、可靠性评分
"""
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, Enum
from sqlalchemy.sql import func
from backend.app.core.config import Base


class Skill(Base):
    """技能模型"""
    __tablename__ = "skill"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    name = Column(String(200), nullable=False, comment="技能标准名称")
    category = Column(String(100), comment="技能类别(编程语言/框架/数据库/工具/中间件/DevOps/AI)")
    description = Column(Text, comment="技能描述")

    # 能力级别
    level = Column(
        Enum("beginner", "intermediate", "advanced", "expert"),
        nullable=False,
        default="intermediate",
        comment="默认能力级别: 入门/进阶/高级/专家"
    )

    # 别名（解决"Vue"/"Vue.js"/"Vue3"同一技能问题）
    aliases = Column(Text, comment='别名列表JSON ["Vue.js","Vue3"]')

    # 状态与可靠性
    status = Column(
        Enum("active", "deprecated", "draft"),
        nullable=False,
        default="active",
        comment="状态: 正常/已废弃/草稿"
    )
    reliability = Column(Integer, nullable=False, default=80, comment="可靠性评分0-100")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<Skill(id={self.id}, name='{self.name}')>"
