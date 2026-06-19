"""
数据库模型 - 岗位-技能关系表 (从JD_py迁移)
需求覆盖：必备vs加分技能、能力变更追踪、重要性等级
"""
from sqlalchemy import Column, BigInteger, Boolean, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.core.config import Base


class PositionSkillRelation(Base):
    """岗位-技能关系模型"""
    __tablename__ = "position_skill_relation"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    position_id = Column(BigInteger, ForeignKey("position.id"), nullable=False, comment="岗位ID")
    skill_id = Column(BigInteger, ForeignKey("skill.id"), nullable=False, comment="技能ID")

    # 重要度等级 1-5
    importance = Column(Integer, nullable=False, default=3,
                        comment="重要度等级 1-5 (1=基础 2=一般 3=重要 4=核心 5=关键)")

    # 是否必需
    is_required = Column(Boolean, nullable=False, default=True, comment="是否必需")

    # 技能类型
    skill_type = Column(
        Enum("required", "preferred", "bonus"),
        nullable=False,
        default="required",
        comment="技能类型: 必备/加分/额外加分"
    )

    # 版本追踪
    version = Column(Integer, nullable=False, default=1, comment="关系版本号")
    change_type = Column(
        Enum("added", "modified", "removed", "unchanged"),
        nullable=False,
        default="added",
        comment="变更类型: 新增/修改/删除/无变化"
    )
    change_reason = Column(String(500), comment="变更原因说明")
    source_note = Column(String(200), comment="数据来源备注")

    # 有效性
    is_valid = Column(Boolean, nullable=False, default=True, comment="是否有效(软删除)")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    position = relationship("Position", backref="skill_relations")
    skill = relationship("Skill", backref="position_relations")

    def __repr__(self):
        return f"<PositionSkillRelation(position_id={self.position_id}, skill_id={self.skill_id})>"
