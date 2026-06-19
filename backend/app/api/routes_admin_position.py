"""
岗位管理 API 路由 (新增)
路径前缀: /api
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict

from backend.app.core.config import get_db, DB_AVAILABLE
from backend.app.services.position_service import PositionService

router = APIRouter(prefix="/positions", tags=["岗位管理"])


# ============================================
# 请求/响应模型
# ============================================
class PositionCreate(BaseModel):
    """创建岗位请求"""
    name: str = Field(..., min_length=1, max_length=200, description="岗位名称")
    description: Optional[str] = Field(None, description="岗位描述")
    core_responsibilities: Optional[str] = Field(None, description="核心职责")
    industry_scenarios: Optional[str] = Field(None, description="行业场景")
    is_new_position: bool = Field(False, description="是否为新岗位")
    similarity_threshold: Optional[str] = Field(None, description="相似度阈值")


class PositionUpdate(BaseModel):
    """更新岗位请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    core_responsibilities: Optional[str] = None
    industry_scenarios: Optional[str] = None
    is_new_position: Optional[bool] = None
    similarity_threshold: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|archived)$")


class PositionResponse(BaseModel):
    """岗位响应"""
    id: int
    name: str
    description: Optional[str]
    status: str
    version: int
    is_new_position: bool
    created_at: Any
    
    class Config:
        from_attributes = True


class SkillRelationCreate(BaseModel):
    """添加技能关系请求"""
    skill_id: int = Field(..., description="技能ID")
    importance: int = Field(3, ge=1, le=5, description="重要度 1-5")
    is_required: bool = Field(True, description="是否必需")
    skill_type: str = Field("required", pattern="^(required|preferred|bonus)$")


# ============================================
# 接口实现
# ============================================

@router.get("", response_model=List[PositionResponse], summary="获取所有岗位")
async def list_positions(db=Depends(get_db)):
    """
    获取所有有效岗位列表
    
    - 支持分页（后续可扩展）
    - 只返回状态为 active 的岗位
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    positions = service.get_all_positions()
    
    return [
        PositionResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            version=p.version,
            is_new_position=p.is_new_position,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in positions
    ]


@router.get("/new", response_model=List[PositionResponse], summary="获取新发现的岗位")
async def list_new_positions(db=Depends(get_db)):
    """获取标记为新发现的岗位（用于人工确认）"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    positions = service.get_new_positions()
    
    return [
        PositionResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            version=p.version,
            is_new_position=p.is_new_position,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in positions
    ]


@router.get("/{position_id}", response_model=PositionResponse, summary="获取岗位详情")
async def get_position(position_id: int, db=Depends(get_db)):
    """根据ID获取岗位详细信息"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    position = service.get_position_by_id(position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在")
    
    return PositionResponse(
        id=position.id,
        name=position.name,
        description=position.description,
        status=position.status,
        version=position.version,
        is_new_position=position.is_new_position,
        created_at=position.created_at.isoformat() if position.created_at else None,
    )


@router.post("", response_model=PositionResponse, summary="创建岗位")
async def create_position(data: PositionCreate, db=Depends(get_db)):
    """
    创建新岗位
    
    - 支持标记为新发现岗位
    - 自动设置初始版本号为1
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    position = service.create_position(data.model_dump())
    
    return PositionResponse(
        id=position.id,
        name=position.name,
        description=position.description,
        status=position.status,
        version=position.version,
        is_new_position=position.is_new_position,
        created_at=position.created_at.isoformat() if position.created_at else None,
    )


@router.put("/{position_id}", response_model=PositionResponse, summary="更新岗位")
async def update_position(position_id: int, data: PositionUpdate, db=Depends(get_db)):
    """更新岗位信息"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    position = service.update_position(position_id, data.model_dump(exclude_unset=True))
    
    if not position:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在")
    
    return PositionResponse(
        id=position.id,
        name=position.name,
        description=position.description,
        status=position.status,
        version=position.version,
        is_new_position=position.is_new_position,
        created_at=position.created_at.isoformat() if position.created_at else None,
    )


@router.delete("/{position_id}", summary="删除岗位")
async def delete_position(position_id: int, db=Depends(get_db)):
    """
    删除岗位（软删除，标记为归档）
    
    - 不会物理删除数据
    - 关联的匹配历史仍可查询
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    success = service.delete_position(position_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在")
    
    return {"message": "岗位已归档", "id": position_id}


@router.post("/{position_id}/confirm", summary="确认新岗位")
async def confirm_new_position(position_id: int, db=Depends(get_db)):
    """
    确认新发现的岗位为标准岗位
    
    - 取消新岗位标记
    - 可用于人工审核流程
    """
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    success = service.mark_as_confirmed(position_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在或不是新岗位")
    
    return {"message": "岗位已确认为标准岗位", "id": position_id}


@router.get("/{position_id}/skills", summary="获取岗位技能列表")
async def get_position_skills(position_id: int, db=Depends(get_db)):
    """获取岗位关联的所有技能及重要性等级"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    
    # 先验证岗位是否存在
    position = service.get_position_by_id(position_id)
    if not position:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在")
    
    skills = service.get_position_skills(position_id)
    
    return [
        {
            "id": s.id,
            "skill_id": s.skill_id,
            "importance": s.importance,
            "is_required": s.is_required,
            "skill_type": s.skill_type,
            "change_type": s.change_type,
        }
        for s in skills
    ]


@router.post("/{position_id}/skills", summary="为岗位添加技能")
async def add_skill_to_position(position_id: int, data: SkillRelationCreate, db=Depends(get_db)):
    """为岗位添加技能关联关系"""
    if not db:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    service = PositionService(db)
    
    # 验证岗位存在
    position = service.get_position_by_id(position_id)
    if not position:
        raise HTTPException(status_code=404, detail=f"岗位 {position_id} 不存在")
    
    relation = service.add_skill_to_position(
        position_id=position_id,
        skill_id=data.skill_id,
        importance=data.importance,
        is_required=data.is_required,
        skill_type=data.skill_type,
    )
    
    return {
        "message": "技能已添加到岗位",
        "relation_id": relation.id,
        "position_id": position_id,
        "skill_id": data.skill_id,
    }
