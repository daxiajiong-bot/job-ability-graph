"""
Shared path and runtime configuration for the enhanced backend.
整合Demo原有配置 + JD_py的数据库配置
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


# ============================================
# 路径配置 (Demo原有)
# ============================================
BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
SAMPLE_DIR = DATA_DIR / "samples"
FRONTEND_DIR = BASE_DIR / "frontend"


# ============================================
# 应用设置 (从JD_py迁移 + Demo原有)
# ============================================
class Settings(BaseSettings):
    """应用配置 - 支持环境变量覆盖"""
    
    # 数据库配置 (从JD_py迁移)
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "jd_matching_system"
    
    # 应用配置 (从JD_py迁移)
    APP_NAME: str = "Job Ability Graph System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True
    
    # API配置
    API_PREFIX: str = "/api"
    
    # Demo原有配置
    USE_LLM: bool = False
    DEFAULT_GRAPH_VERSION: str = "demo-v1"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 创建配置实例
settings = Settings()


# ============================================
# 数据库连接 (从JD_py迁移)
# ============================================

def _create_database_if_not_exists():
    """如果数据库不存在则创建"""
    try:
        DATABASE_URL_NO_DB = f"mysql+mysqldb://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}"
        temp_engine = create_engine(DATABASE_URL_NO_DB, pool_pre_ping=True)
        
        with temp_engine.connect() as conn:
            create_db_sql = text(
                f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME} "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.execute(create_db_sql)
            conn.commit()
        temp_engine.dispose()
        print(f"✓ 数据库 {settings.DB_NAME} 已就绪")
    except Exception as e:
        print(f"⚠ 数据库初始化警告: {e}")
        print("  将使用JSON文件作为备用存储")


# 初始化数据库（可选，失败不影响运行）
_create_database_if_not_exists()

# 构建数据库连接URL
DATABASE_URL = f"mysql+mysqldb://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# 创建数据库引擎
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=settings.DEBUG
    )
    
    # 创建会话工厂
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # 创建基类
    Base = declarative_base()
    
    DB_AVAILABLE = True
    print("✓ MySQL数据库连接成功")
except Exception as e:
    print(f"⚠ MySQL连接失败: {e}")
    print("  系统将使用JSON文件存储模式")
    engine = None
    SessionLocal = None
    Base = None
    DB_AVAILABLE = False


# ============================================
# 备用基类（当数据库不可用时使用）
# ============================================
if Base is None:
    # 创建一个虚拟基类，支持模型定义但不连接数据库
    class _FallbackBase:
        """备用基类 - 当MySQL不可用时使用"""
        def __init_subclass__(cls, **kwargs):
            pass  # 允许定义子类但不注册到ORM
        @classmethod
        def __init__(self, *args, **kwargs):
            pass

    Base = _FallbackBase


def get_db():
    """
    获取数据库会话
    如果数据库不可用，返回None（服务层会自动降级到JSON存储）
    """
    if not DB_AVAILABLE or SessionLocal is None:
        return None
        
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db_tables():
    """初始化数据库表"""
    if DB_AVAILABLE and Base is not None:
        try:
            Base.metadata.create_all(bind=engine)
            print("✓ 数据库表创建成功")
        except Exception as e:
            print(f"⚠ 数据库表创建失败: {e}")


__all__ = [
    "BASE_DIR", "DATA_DIR", "SAMPLE_DIR", "FRONTEND_DIR",
    "settings", "DB_AVAILABLE",
    "engine", "SessionLocal", "Base", "get_db", "init_db_tables",
    # 导出常用配置项（供其他模块直接导入）
    "DEFAULT_GRAPH_VERSION", "USE_LLM",
]

# ============================================
# 常用配置快捷访问（兼容旧代码）
# ============================================
DEFAULT_GRAPH_VERSION: str = settings.DEFAULT_GRAPH_VERSION
USE_LLM: bool = settings.USE_LLM
