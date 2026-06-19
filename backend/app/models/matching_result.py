"""
数据库模型 - 匹配结果表 (从JD_py迁移)
需求覆盖：人岗匹配诊断、多维度分析、学习路径规划
"""
from sqlalchemy import Column, BigInteger, Text, Boolean, DECIMAL, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.core.config import Base


class MatchingResult(Base):
    """匹配结果模型"""
    __tablename__ = "matching_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")

    # 关联关系（兼容多种模式）
    jd_id = Column(BigInteger, ForeignKey("jd.id"), comment="JD ID(可为空)")
    resume_id = Column(BigInteger, ForeignKey("resume.id"), comment="简历ID(可为空)")
    position_id = Column(BigInteger, ForeignKey("position.id"), nullable=False, comment="目标岗位ID")

    # 匹配模式
    match_mode = Column(
        Enum("jd_vs_resume", "skill_vs_position"),
        nullable=False,
        default="skill_vs_position",
        comment="匹配模式: JD对比简历 / 技能对比岗位图谱"
    )

    # 匹配分数
    match_score = Column(DECIMAL(5, 4), nullable=False, comment="总体匹配分数 0-1")
    match_reason = Column(Text, comment="匹配理由摘要")

    # 差距分析
    gap_analysis = Column(JSON, comment='差距分析详情')

    # 多维度分数
    dimension_scores = Column(JSON, comment='各维度匹配分')

    # 用户提交时的技能快照
    user_skills_snapshot = Column(JSON, comment='用户提交的技能快照')

    # 推荐技能
    recommended_skills = Column(JSON, comment="推荐补足的技能列表")

    # 学习路径规划
    learning_path = Column(JSON, comment='学习路径规划')

    # 测试标记
    is_test_result = Column(Boolean, nullable=False, default=False, comment="是否为测试结果")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    # 关系
    jd = relationship("Jd", backref="matching_results")
    resume = relationship("Resume", backref="matching_results")
    position = relationship("Position", backref="matching_results")

    def __repr__(self):
        return f"<MatchingResult(id={self.id}, score={self.match_score})>"
