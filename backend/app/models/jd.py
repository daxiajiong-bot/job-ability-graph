"""
数据库模型 - JD表 (从JD_py迁移)
需求覆盖：多源异构数据管理、解析置信度跟踪
"""
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DECIMAL, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.core.config import Base


class Jd(Base):
    """JD模型"""
    __tablename__ = "jd"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    title = Column(String(200), nullable=False, comment="职位标题")
    company = Column(String(200), comment="公司名称")
    raw_content = Column(Text, nullable=False, comment="原始JD文本内容")
    structured_data = Column(JSON, comment="AI解析后的结构化结果")
    position_id = Column(BigInteger, ForeignKey("position.id"), comment="关联的标准岗位ID")

    # 多源数据管理
    source = Column(
        String(100),
        nullable=False,
        default="manual",
        comment="数据来源(boss/zhipin/lagou/liepin/crawler/manual/upload)"
    )
    source_url = Column(String(500), comment="原始链接URL")
    confidence = Column(DECIMAL(3, 2), nullable=False, default=0.80,
                       comment="解析置信度 0-1")

    # 测试标记
    is_test_case = Column(Boolean, nullable=False, default=False, comment="是否为测试用例JD")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    position = relationship("Position", backref="jds")

    def __repr__(self):
        return f"<Jd(id={self.id}, title='{self.title}')>"
