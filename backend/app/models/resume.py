"""
数据库模型 - 简历表 (从JD_py迁移)
需求覆盖：简历PDF/Word上传、解析状态跟踪
"""
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DECIMAL, DateTime, Enum, JSON
from sqlalchemy.sql import func
from backend.app.core.config import Base


class Resume(Base):
    """简历模型"""
    __tablename__ = "resume"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id = Column(BigInteger, comment="用户ID")
    name = Column(String(100), nullable=False, comment="候选人姓名")
    email = Column(String(100), comment="邮箱")
    phone = Column(String(20), comment="电话")

    # 提取后的文本内容
    raw_content = Column(Text, comment="提取后的文本内容")
    
    # 结构化解析结果
    structured_data = Column(JSON, comment="结构化解析结果")

    # 文件存储信息
    file_path = Column(String(500), comment="原始文件存储路径")
    file_type = Column(String(20), comment="文件类型(pdf/docx/doc/txt)")
    file_size = Column(BigInteger, comment="文件大小(字节)")

    # 解析状态跟踪
    parse_status = Column(
        Enum("pending", "parsing", "completed", "failed"),
        nullable=False,
        default="pending",
        comment="解析状态: 待解析/解析中/已完成/失败"
    )
    parse_confidence = Column(DECIMAL(3, 2), comment="简历解析置信度 0-1")
    parse_error = Column(Text, comment="解析错误信息")
    parsed_at = Column(DateTime, comment="解析完成时间")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<Resume(id={self.id}, name='{self.name}')>"
