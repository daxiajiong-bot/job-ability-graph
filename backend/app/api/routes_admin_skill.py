"""
技能管理 API 路由 (新增)
路径前缀: /api
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any

from backend.app.core.config import get_db, DB_AVAILABLE
from backend.app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["技能管理"])


# ============================================
# 请求/响应模型
# ============================================
class SkillCreate(BaseModel):
    """创建技能请求"""
    name: str = Field(..., min_length=1, max_length=200, description="技能名称")
    category: Optional[str] = Field(None, max_length=100, description="技能类别")
    description: Optional[str] = Field(None, description="技能描述")
    level: str = Field("intermediate", pattern="^(beginner|intermediate|advanced|expert)$")
    reliability: int = Field(80, ge=0, le=100, description="可靠性评分")


class SkillUpdate(BaseModel):
    """更新技能请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    level: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced|expert)$")
    reliability: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, pattern="^(active|deprecated|draft)$")


class SkillResponse(BaseModel):
    """技能响应"""
    id: int
    name: str
    category: Optional[str]
    level: str
    status: str
    reliability: int
    created_at: Any
    
    class Config:
        from_attributes = True


class SkillBatchCreate(BaseModel):
    """批量创建技能请求"""
    skills: List[SkillCreate] = Field(..., min_length=1, description="技能列表")


# ============================================
# 接口实现
# ============================================

@router.get("", response_model=List[SkillResponse], summary="获取所有技能")
async def list_skills(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db=Depends(get_db)
):
    """
    获取技能列表
    
    - 支持按类别筛选
    - 支持关键词搜索
    - 只返回有效技能
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    
    if search:
        skills = service.search_skills(search)
    elif category:
        skills = service.get_skills_by_category(category)
    else:
        skills = service.get_all_skills()
    
    return [
        SkillResponse(
            id=s.id,
            name=s.name,
            category=s.category,
            level=s.level,
            status=s.status,
            reliability=s.reliability,
            created_at=s.created_at.isoformat() if s.created_at else None,
        )
        for s in skills
    ]


@router.get("/categories", summary="获取技能类别列表")
async def list_categories(db=Depends(get_db)):
    """获取所有技能类别（用于前端下拉选择）"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    categories = service.get_categories()
    
    return {"categories": categories, "count": len(categories)}


@router.get("/{skill_id}", response_model=SkillResponse, summary="获取技能详情")
async def get_skill(skill_id: int, db=Depends(get_db)):
    """根据ID获取技能详细信息"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    skill = service.get_skill_by_id(skill_id)
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        category=skill.category,
        level=skill.level,
        status=skill.status,
        reliability=skill.reliability,
        created_at=skill.created_at.isoformat() if skill.created_at else None,
    )


@router.post("", response_model=SkillResponse, summary="创建技能")
async def create_skill(data: SkillCreate, db=Depends(get_db)):
    """
    创建新技能
    
    - 支持设置默认能力级别
    - 支持设置可靠性评分
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    skill = service.create_skill(data.model_dump())
    
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        category=skill.category,
        level=skill.level,
        status=skill.status,
        reliability=skill.reliability,
        created_at=skill.created_at.isoformat() if skill.created_at else None,
    )


@router.post("/batch", summary="批量创建技能")
async def create_skills_batch(data: SkillBatchCreate, db=Depends(get_db)):
    """
    批量创建技能
    
    - 用于初始化技能库
    - 返回创建成功的技能数量和列表
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    skills = service.create_skills_batch([s.model_dump() for s in data.skills])
    
    return {
        "message": f"批量创建成功",
        "count": len(skills),
        "skills": [
            {"id": s.id, "name": s.name}
            for s in skills
        ]
    }


@router.put("/{skill_id}", response_model=SkillResponse, summary="更新技能")
async def update_skill(skill_id: int, data: SkillUpdate, db=Depends(get_db)):
    """更新技能信息"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    skill = service.update_skill(skill_id, data.model_dump(exclude_unset=True))
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        category=skill.category,
        level=skill.level,
        status=skill.status,
        reliability=skill.reliability,
        created_at=skill.created_at.isoformat() if skill.created_at else None,
    )


@router.delete("/{skill_id}", summary="删除技能")
async def delete_skill(skill_id: int, db=Depends(get_db)):
    """
    删除技能（软删除，标记为废弃）
    
    - 已关联的岗位不受影响
    - 历史匹配记录仍可查看
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = SkillService(db)
    success = service.delete_skill(skill_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    
    return {"message": "技能已废弃", "id": skill_id}
