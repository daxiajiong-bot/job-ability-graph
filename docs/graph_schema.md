# 图谱 Schema

## 节点格式

```json
{
  "id": "skill:python",
  "label": "Python",
  "type": "Skill",
  "level": 2,
  "properties": {}
}
```

字段说明：

- `id`：稳定 ID，便于多次运行后对齐节点；
- `label`：展示名称；
- `type`：节点类型；
- `level`：可选能力等级；
- `properties`：扩展属性，例如来源、权重、证据 ID、视图类型等。

支持的节点类型：

- `Position`：岗位；
- `Capability`：能力域；
- `TechStack`：技术栈；
- `Skill`：技能点；
- `Level`：能力等级；
- `Candidate`：候选人；
- `Evidence`：证据；
- `Version`：时间/版本。

## 边格式

```json
{
  "source": "position:xxx",
  "target": "skill:python",
  "relation": "requires_skill",
  "weight": 1.2,
  "properties": {}
}
```

主要关系：

- `requires_skill`：岗位要求技能；
- `requires_capability`：岗位要求能力域；
- `contains_skill`：能力域包含技能；
- `belongs_to_stack`：技能属于技术栈；
- `has_skill`：候选人具备技能；
- `supports`：证据支持画像或技能；
- `matches`：候选人与岗位技能匹配；
- `lacks`：候选人缺失岗位技能；
- `partially_matches`：候选人部分满足岗位技能；
- `newly_requires`：新版岗位新增技能要求；
- `rising_in`：技能在新岗位/新版本中上升；
- `declining_in`：技能在新版本中下降或弱化。

## 视图图谱

| 视图 | 文件 | 现场讲解重点 |
| --- | --- | --- |
| position | `graph_position_view.json` | 岗位 -> 能力域 -> 技能点 |
| tech_stack | `graph_tech_stack_view.json` | 技术栈 -> 技能点 -> 岗位 |
| level | `graph_level_view.json` | 岗位要求等级与候选人熟练度 |
| match | `graph_match_view.json` | 命中、缺失、部分匹配技能 |
| evolution | `graph_evolution_view.json` | 新增、上升、下降技能和版本变化 |
