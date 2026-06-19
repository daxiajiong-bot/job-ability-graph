"""
FastAPI application entrypoint for the enhanced backend.
整合Demo原有功能 + JD_py的管理功能
"""

from __future__ import annotations
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（支持从任何位置启动）
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/app -> job-ability-graph
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import (
    settings, DB_AVAILABLE, init_db_tables, FRONTEND_DIR
)

# Demo原有路由（保持不变）
from backend.app.api.routes_evolution import router as evolution_router
from backend.app.api.routes_graph import router as graph_router
from backend.app.api.routes_match import router as match_router
from backend.app.api.routes_parse import router as parse_router

# 新增管理路由（从JD_py迁移）
from backend.app.api.routes_admin_position import router as position_admin_router
from backend.app.api.routes_admin_skill import router as skill_admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：初始化数据库表
    print("\n" + "="*60)
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    print("="*60 + "\n")
    
    if DB_AVAILABLE:
        init_db_tables()
    
    yield
    
    # 关闭时
    print("\n" + "="*60)
    print("👋 应用已关闭")
    print("="*60 + "\n")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## Job Ability Graph System - 整合版后端

### 功能模块：

#### 📝 Demo原有功能（无前缀）
- **JD解析**: `POST /parse/jd` - 解析JD文本，提取岗位画像
- **简历解析**: `POST /parse/resume` - 解析简历文本，提取候选人画像
- **人岗匹配**: `POST /match` - JD与简历的匹配分析
- **图谱视图**: `GET /graph/view` - 岗位能力图谱展示
- **演化分析**: 
  - `POST /evolution/discover` - 新岗位发现
  - `POST /evolution/update` - 岗位能力动态更新

#### 🔧 管理功能（/api前缀）
- **岗位管理**: `/api/positions/*` - CRUD + 技能关联
- **技能管理**: `/api/skills/*` - CRUD + 类别管理

### 数据存储：
- ✅ MySQL数据库（主存储，用于管理和历史记录）
- 📁 JSON文件（备用存储，用于Demo算法产物）

### 特性：
- 🔄 双模式存储：数据库 + JSON文件自动同步
- 🛡️ 优雅降级：数据库不可用时自动使用JSON文件
- 📊 完整的CRUD接口：支持前端管理系统
- 🔍 强大的搜索和筛选功能
""",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# 注册路由
# ============================================

# Demo原有路由（无前缀，保持向后兼容）
app.include_router(parse_router)      # /parse/*
app.include_router(match_router)      # /match
app.include_router(graph_router)     # /graph/*
app.include_router(evolution_router) # /evolution/*

# 新增管理路由（带/api前缀）
admin_router = admin = APIRouter(prefix="/api")
admin_router.include_router(position_admin_router)  # /api/positions/*
admin_router.include_router(skill_admin_router)     # /api/skills/*
app.include_router(admin_router)


# ============================================
# 静态文件服务（Demo原有）
# ============================================
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ============================================
# 根路由和健康检查
# ============================================

@app.get("/", include_in_schema=False)
def index() -> object:
    """
    根路径
    
    - 如果存在Demo前端，返回index.html
    - 否则返回API信息
    """
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if DB_AVAILABLE else "disconnected (using JSON)",
        "docs": "/docs",
        "endpoints": {
            "demo": {
                "parse_jd": "/parse/jd",
                "parse_resume": "/parse/resume",
                "match": "/match",
                "graph_view": "/graph/view",
                "evolution": "/evolution/discover",
            },
            "admin": {
                "positions": "/api/positions",
                "skills": "/api/skills",
            }
        }
    }


@app.get("/health")
def health() -> dict:
    """
    健康检查端点
    
    返回系统状态信息
    """
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if DB_AVAILABLE else "disconnected",
        "db_available": DB_AVAILABLE,
    }


@app.get("/info")
def info() -> dict:
    """
    系统信息端点
    
    返回详细的系统配置信息
    """
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "use_llm": settings.USE_LLM,
        "storage_mode": "mysql+json" if DB_AVAILABLE else "json_only",
        "features": {
            "jd_parsing": True,
            "resume_parsing": True,
            "job_matching": True,
            "graph_building": True,
            "evolution_analysis": True,
            "position_management": True,
            "skill_management": True,
            "db_persistence": DB_AVAILABLE,
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    print("""
╔══════════════════════════════════════════════════╗
║                                                  ║
║   🚀 Job Ability Graph System - Enhanced Backend ║
║                                                  ║
║   整合版: Demo算法 + 数据库管理                   ║
║                                                  ║
╚══════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 临时禁用自动重载以避免崩溃
        log_level="info",
    )
