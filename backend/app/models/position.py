"""
数据库模型 - 岗位表 (从JD_py迁移)
需求覆盖：新岗位发现与定义（核心职责/行业场景/数据来源）
"""
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, Enum, Integer
from sqlalchemy.sql import func
from backend.app.core.config import Base


class Position(Base):
    """岗位模型"""
    __tablename__ = "position"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    name = Column(String(200), nullable=False, comment="岗位名称")
    description = Column(Text, comment="岗位概述")
    
    # 岗位定义结构化
    core_responsibilities = Column(Text, comment='核心职责列表JSON')
    industry_scenarios = Column(String(500), comment="典型行业应用场景，逗号分隔")

    # 状态管理
    status = Column(
        Enum("active", "archived"),
        nullable=False,
        default="active",
        comment="状态: 有效/已归档"
    )
    data_source = Column(String(100), comment="数据来源(爬虫聚合/人工录入/AI生成)")
    version = Column(Integer, nullable=False, default=1, comment="版本号")
    
    # 新岗位标记
    is_new_position = Column(Boolean, nullable=False, default=False, comment="是否为新发现岗位")
    similarity_threshold = Column(String(20), comment="新岗位识别相似度阈值")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<Position(id={self.id}, name='{self.name}')>"
