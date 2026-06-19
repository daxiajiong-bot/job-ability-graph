"""
技能服务 - 技能管理 (从JD_py迁移)
"""
from typing import List, Optional
import logging

from backend.app.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillService:
    """技能服务类"""
    
    def __init__(self, db):
        self.db = db
    
    def get_all_skills(self) -> List[Skill]:
        """获取所有有效技能"""
        return self.db.query(Skill).filter(Skill.status == "active").all()
    
    def get_skill_by_id(self, skill_id: int) -> Optional[Skill]:
        """根据ID获取技能"""
        return self.db.query(Skill).filter(Skill.id == skill_id).first()
    
    def search_skills(self, name: str) -> List[Skill]:
        """搜索技能（模糊匹配）"""
        return self.db.query(Skill).filter(
            Skill.name.contains(name),
            Skill.status == "active"
        ).all()
    
    def get_skills_by_category(self, category: str) -> List[Skill]:
        """根据类别获取技能"""
        return self.db.query(Skill).filter(
            Skill.category == category,
            Skill.status == "active"
        ).all()
    
    def get_categories(self) -> List[str]:
        """获取所有技能类别"""
        results = self.db.query(Skill.category).filter(
            Skill.status == "active",
            Skill.category.isnot(None)
        ).distinct().all()
        return [r[0] for r in results if r[0]]
    
    def create_skill(self, data: dict) -> Skill:
        """
        创建技能
        
        Args:
            data: 包含name, category, description等字段的字典
        """
        skill = Skill(
            name=data.get("name", ""),
            category=data.get("category"),
            description=data.get("description"),
            level=data.get("level", "intermediate"),
            aliases=data.get("aliases"),
            reliability=data.get("reliability", 80),
        )
        
        self.db.add(skill)
        self.db.commit()
        self.db.refresh(skill)
        
        logger.info(f"✓ 创建技能成功 (id={skill.id}, name='{skill.name}')")
        return skill
    
    def update_skill(self, skill_id: int, data: dict) -> Optional[Skill]:
        """更新技能"""
        skill = self.get_skill_by_id(skill_id)
        if not skill:
            return None
        
        if data.get("name"):
            skill.name = data["name"]
        if data.get("category"):
            skill.category = data["category"]
        if data.get("description") is not None:
            skill.description = data["description"]
        if data.get("level"):
            skill.level = data["level"]
        if data.get("aliases") is not None:
            skill.aliases = data["aliases"]
        if data.get("reliability") is not None:
            skill.reliability = data["reliability"]
        if data.get("status"):
            skill.status = data["status"]
        
        self.db.commit()
        self.db.refresh(skill)
        
        logger.info(f"✓ 更新技能成功 (id={skill_id})")
        return skill
    
    def delete_skill(self, skill_id: int) -> bool:
        """软删除技能（标记为废弃）"""
        skill = self.get_skill_by_id(skill_id)
        if skill:
            skill.status = "deprecated"
            self.db.commit()
            logger.info(f"✓ 技能已废弃 (id={skill_id})")
            return True
        return False
    
    def create_skills_batch(self, skills_data: List[dict]) -> List[Skill]:
        """
        批量创建技能
        
        Args:
            skills_data: 技能数据字典列表
        """
        skills = []
        for data in skills_data:
            skill = Skill(
                name=data.get("name", ""),
                category=data.get("category"),
                description=data.get("description"),
                level=data.get("level", "intermediate"),
                reliability=data.get("reliability", 80),
            )
            skills.append(skill)
        
        self.db.add_all(skills)
        self.db.commit()
        
        for skill in skills:
            self.db.refresh(skill)
        
        logger.info(f"✓ 批量创建技能成功，数量: {len(skills)}")
        return skills
    
    def get_skill_count(self) -> int:
        """获取技能总数"""
        return self.db.query(Skill).filter(Skill.status == "active").count()
    
    def find_or_create(self, name: str, category: str = None) -> Skill:
        """
        查找或创建技能（用于解析时自动入库）
        
        Args:
            name: 技能名称
            category: 技能类别（可选）
        """
        # 先尝试精确查找
        skill = self.db.query(Skill).filter(
            Skill.name == name,
            Skill.status == "active"
        ).first()
        
        if skill:
            return skill
        
        # 不存在则创建
        return self.create_skill({
            "name": name,
            "category": category,
            "data_source": "auto_extracted",
        })
