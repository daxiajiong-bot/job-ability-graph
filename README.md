# job-ability-graph

面向“多源异构数据驱动岗位和能力图谱构建与动态演化分析”赛题的 FastAPI demo。系统以规则算法为默认主链路，完成 JD 解析、简历解析、人岗匹配、能力差距分析、岗位能力图谱、图谱视图、新岗位发现、岗位能力动态更新，并预留安全的 LLM 增强层。

## 赛题对应关系

| 赛题能力 | 当前实现 |
| --- | --- |
| JD 解析 | `/parse/jd` 输出岗位结构化画像、技能权重、证据 |
| 简历解析 | `/parse/resume` 输出候选人画像、技能熟练度、证据 |
| 人岗匹配 | `/match` 输出分数、决策、命中/缺失/部分匹配技能 |
| 能力差距分析 | `match_result.gap_analysis` 和 `partial_skills/missing_skills` |
| 岗位能力图谱 | `data/graph/graph_full.json`，节点含 Position、Capability、Skill 等 |
| 技术栈/等级/匹配/演化视图 | `/graph/view?view_type=tech_stack|level|match|evolution` |
| 新岗位发现 | `/evolution/discover` 聚合多条 JD 来源 |
| 岗位动态更新 | `/evolution/update` 对比旧版/新版 JD 能力变化 |
| LLM 增强预留 | `backend/app/llm/*`，默认 `use_llm=false`，不接真实 API |

## 技术路线

```text
Raw JD/Resume
  -> API routes
  -> Service orchestration
  -> Rule parsers + skill normalizer
  -> Skill profile builder
  -> Rule matcher + gap analyzer
  -> Unified graph builder + graph views
  -> JSON storage artifacts
```

LLM 只作为旁路增强入口：JD/简历抽取、匹配解释、新岗位命名、岗位更新说明。当前未配置真实 LLM 时返回 `llm_used=false`，不会覆盖规则结果，也不会改变匹配分数。

## 目录结构

```text
backend/app/
  api/          # routes_parse/routes_match/routes_graph/routes_evolution
  services/     # parse/match/graph/evolution/ingest 编排
  algorithms/   # 规则解析、归一化、匹配、差距分析
  graph/        # graph_schema、graph_builder、graph_views、graph_repository
  storage/      # paths、id_generator、json_store
  llm/          # 安全 LLM 预留层和 prompt 模板
  schemas/      # Pydantic 请求/响应模型
data/
  samples/      # 样例 JD 和简历
  raw/          # 原始文本落盘
  parsed/       # JD/Resume profile
  normalized/   # 技能归一化结果
  evidence/     # evidence_index.json
  matches/      # 匹配结果
  graph/        # graph_full 和视图图谱
  evaluation/   # 评测结果
scripts/
docs/
frontend/
```

## 数据保存机制

运行解析或匹配后，系统会按层保存 JSON：

- `data/raw/jd/*.json`、`data/raw/resume/*.json`
- `data/parsed/jd_profiles/*.json`、`data/parsed/resume_profiles/*.json`
- `data/normalized/*.json`
- `data/evidence/evidence_index.json`
- `data/matches/*.json`
- `data/graph/graph_full.json`
- `data/graph/graph_position_view.json`
- `data/graph/graph_tech_stack_view.json`
- `data/graph/graph_level_view.json`
- `data/graph/graph_match_view.json`
- `data/graph/graph_evolution_view.json`
- `data/evaluation/evaluation_result.json`

ID 由 `backend/app/storage/id_generator.py` 稳定生成，不使用随机 `node_1` 之类的不稳定 ID。

## 知识图谱 Schema

统一图谱结构：

```json
{
  "graph_id": "graph_full",
  "version": "demo-v1",
  "generated_at": "...",
  "nodes": [{"id": "...", "label": "...", "type": "Skill", "level": 2, "properties": {}}],
  "edges": [{"source": "...", "target": "...", "relation": "requires_skill", "weight": 1.0, "properties": {}}],
  "metadata": {}
}
```

节点类型：`Position`、`Capability`、`TechStack`、`Skill`、`Level`、`Candidate`、`Evidence`、`Version`。

核心关系：`requires_skill`、`requires_capability`、`contains_skill`、`belongs_to_stack`、`has_skill`、`supports`、`matches`、`lacks`、`partially_matches`、`newly_requires`、`rising_in`、`declining_in`。

## 安装依赖

```bash
cd job-ability-graph-main
python3 -m pip install -r requirements.txt
```

## 启动后端

```bash
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

可视化工作台：

```text
http://127.0.0.1:8000/
```

## 运行 Smoke Test

```bash
python3 scripts/smoke_test.py
```

该脚本会验证 API 路由、样例解析、匹配、LLM 安全旁路、图谱保存和视图文件。

## 运行样例评测

```bash
python3 scripts/evaluate_samples.py
```

输出每个 JD 的 Top-3 简历匹配结果，并保存：

```text
data/evaluation/evaluation_result.json
```

## API 列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| GET | `/samples` | 读取样例 JD/简历 |
| POST | `/parse/jd` | JD 解析，输入 `{"text": "...", "use_llm": false}` |
| POST | `/parse/resume` | 简历解析，输入 `{"text": "...", "use_llm": false}` |
| POST | `/parse/resume-document` | txt/md/pdf/docx 简历文档解析 |
| POST | `/match` | 人岗匹配 |
| GET | `/graph/full` | 读取完整图谱 |
| GET | `/graph/view?view_type=match` | 读取 position/tech_stack/level/match/evolution 视图 |
| POST | `/graph/panorama` | 多岗位全景图谱 |
| POST | `/evolution/discover` | 新岗位发现 |
| POST | `/evolution/update` | 岗位能力动态更新 |
| POST | `/jobs/discover` | 兼容别名 |
| POST | `/jobs/compare` | 兼容别名 |

`/match` 示例：

```bash
curl -X POST http://127.0.0.1:8000/match \
  -H "Content-Type: application/json" \
  -d '{
    "jd_text": "岗位名称: 大模型算法工程师\n任职要求: 熟练掌握 Python、PyTorch、RAG。",
    "resume_text": "姓名: 候选人A\n项目经历: 使用 Python、PyTorch、RAG 完成知识库问答系统。",
    "use_llm": false
  }'
```

## 当前限制

- 不接真实 LLM API；
- 不引入数据库、Neo4j 或向量库；
- 图谱以 JSON 文件保存；
- 前端是轻量原生 HTML/CSS/JS；
- 样例规模较小，评测用于 demo 验证，不代表真实招聘生产效果。

## 后续计划

1. 接入真实多源数据清洗与去重；
2. 扩展技能词表、能力域和技术栈映射；
3. 加入人工审核与版本确认流程；
4. 在 LLM 层接入可配置 provider，并做 JSON schema 校验；
5. 增加时间序列趋势分析和批量评测报告；
6. 按需升级交互式图谱前端。
