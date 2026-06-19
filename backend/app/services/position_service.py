"""
岗位服务 - 岗位和能力图谱管理 (从JD_py迁移)
"""
from typing import List, Optional
import logging

from backend.app.models.position import Position
from backend.app.models.position_skill_relation import PositionSkillRelation

logger = logging.getLogger(__name__)


class PositionService:
    """岗位服务类"""
    
    def __init__(self, db):
        self.db = db
    
    def get_all_positions(self) -> List[Position]:
        """获取所有有效岗位"""
        return self.db.query(Position).filter(Position.status == "active").all()
    
    def get_position_by_id(self, position_id: int) -> Optional[Position]:
        """根据ID获取岗位"""
        return self.db.query(Position).filter(Position.id == position_id).first()
    
    def search_positions(self, name: str) -> List[Position]:
        """搜索岗位（模糊匹配）"""
        return self.db.query(Position).filter(
            Position.name.contains(name),
            Position.status == "active"
        ).all()
    
    def get_new_positions(self) -> List[Position]:
        """获取新发现的岗位"""
        return self.db.query(Position).filter(
            Position.is_new_position == True,
            Position.status == "active"
        ).all()
    
    def create_position(self, data: dict) -> Position:
        """
        创建岗位
        
        Args:
            data: 包含name, description等字段的字典
        """
        position = Position(
            name=data.get("name", ""),
            description=data.get("description"),
            core_responsibilities=data.get("core_responsibilities"),
            industry_scenarios=data.get("industry_scenarios"),
            is_new_position=data.get("is_new_position", False),
            similarity_threshold=data.get("similarity_threshold"),
            data_source=data.get("data_source", "manual"),
        )
        
        self.db.add(position)
        self.db.commit()
        self.db.refresh(position)
        
        logger.info(f"✓ 创建岗位成功 (id={position.id}, name='{position.name}')")
        return position
    
    def update_position(self, position_id: int, data: dict) -> Optional[Position]:
        """更新岗位"""
        position = self.get_position_by_id(position_id)
        if not position:
            return None
        
        # 更新非空字段
        if data.get("name"):
            position.name = data["name"]
        if data.get("description") is not None:
            position.description = data["description"]
        if data.get("is_new_position") is not None:
            position.is_new_position = data["is_new_position"]
        if data.get("similarity_threshold"):
            position.similarity_threshold = data["similarity_threshold"]
        if data.get("status"):
            position.status = data["status"]
        
        # 版本号递增
        position.version += 1
        
        self.db.commit()
        self.db.refresh(position)
        
        logger.info(f"✓ 更新岗位成功 (id={position.id})")
        return position
    
    def delete_position(self, position_id: int) -> bool:
        """软删除岗位（标记为归档）"""
        position = self.get_position_by_id(position_id)
        if position:
            position.status = "archived"
            self.db.commit()
            logger.info(f"✓ 岗位已归档 (id={position_id})")
            return True
        return False
    
    def get_position_skills(self, position_id: int) -> List[PositionSkillRelation]:
        """获取岗位关联的技能列表"""
        return self.db.query(PositionSkillRelation).filter(
            PositionSkillRelation.position_id == position_id,
            PositionSkillRelation.is_valid == True
        ).all()
    
    def add_skill_to_position(self, position_id: int, skill_id: int, **kwargs) -> PositionSkillRelation:
        """为岗位添加技能关系"""
        relation = PositionSkillRelation(
            position_id=position_id,
            skill_id=skill_id,
            importance=kwargs.get("importance", 3),
            is_required=kwargs.get("is_required", True),
            skill_type=kwargs.get("skill_type", "required"),
        )
        
        self.db.add(relation)
        self.db.commit()
        self.db.refresh(relation)
        
        logger.info(f"✓ 岗位-技能关系已创建 (position={position_id}, skill={skill_id})")
        return relation
    
    def mark_as_confirmed(self, position_id: int) -> bool:
        """确认新岗位（取消新岗位标记）"""
        position = self.get_position_by_id(position_id)
        if position and position.is_new_position:
            position.is_new_position = False
            self.db.commit()
            logger.info(f"✓ 岗位已确认为标准岗位 (id={position_id})")
            return True
        return False
    
    def get_position_count(self) -> int:
        """获取岗位总数"""
        return self.db.query(Position).filter(Position.status == "active").count()
