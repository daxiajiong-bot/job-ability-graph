# 9000 条 JD 知识图谱构建报告

## 输入

- `data/output/real_9000/profiles.jsonl`
- 共 9000 条 `jd_profile_v1`

## 图谱 Schema

- 节点：`Job`、`Skill`、`Evidence`、`Education`、`ExperienceRequirement`、`Location`
- 关系：`REQUIRES_SKILL`、`PREFERS_SKILL`、`MENTIONS_SKILL`、`SUPPORTED_BY`、`REQUIRES_EDUCATION`、`REQUIRES_EXPERIENCE`、`LOCATED_IN`

## 构建结果

- 节点数：84269
- 边数：232734
- 图谱状态：`valid`

### 节点统计

- `Job`: 9000
- `Skill`: 225
- `Evidence`: 73149
- `Education`: 9
- `ExperienceRequirement`: 9
- `Location`: 1877

### 关系统计

- `REQUIRES_SKILL`: 49820
- `PREFERS_SKILL`: 14040
- `MENTIONS_SKILL`: 27716
- `SUPPORTED_BY`: 116367
- `REQUIRES_EDUCATION`: 8884
- `REQUIRES_EXPERIENCE`: 6907
- `LOCATED_IN`: 9000

## 有效性检测

- 重复节点 ID: 0
- 重复边 ID: 0
- 非法节点标签: 0
- 非法关系类型: 0
- 悬空边: 0
- 原文证据缺失: 0
- 孤立节点: 0
- 需要关注的岗位（无技能边）: 264

## 结果展示

- 局部子图 JSON: `sample_subgraph_first_5.json`
- 局部子图 Markdown: `sample_subgraph_first_5.md`
- 局部子图 HTML: `sample_subgraph_first_5.html`
- 交互式网页可视化: `web/index.html`
- Top Skills: `top_skills.csv`

## 流程图

- [kg_build_flow.md](../../../docs/kg_build_flow.md)
