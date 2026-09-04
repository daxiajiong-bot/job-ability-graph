# 作品提交（3）测试数据：新岗位 & 既有岗位能力图谱与岗位数据源

对应提交要求“（3）测试数据：1 个新岗位和 1 个既有岗位的能力图谱及岗位数据源（含输入输出示例）”。
本目录全部数据由仓库内真实产物生成，可用生成脚本一键复现。

## 一、样例总览

| 样例 | 岗位 | 输入（数据源） | 输出（能力图谱） |
|---|---|---|---|
| 既有岗位 | **python自动化测试工程师（双休/福利好）**<br>`job:40857992907` | 智联招聘 JD 原文（`input/jd_source.json`） | `output/job_ability_graph.json`：43 节点 / 68 边（1 岗位 → 11 技术 / 4 技能 / 3 知识 → 24 证据） |
| 新岗位 | **AI Agent安全评测工程师**<br>`role:51fda9ea3aba30e88342` | 离线趋势分析候选岗位 + 支撑证据（`input/emerging_role.json`、`input/evidence_sample.json`） | `output/kg_link_delta.json`：8 条增量提案（1 propose_node + 7 能力边）；`output/ability_edges_proposal.json`：新岗位能力边视图 |

## 二、目录结构

```
submission-testdata/
├── README.md                                    本说明
├── tools/
│   └── generate_testdata.py                     生成脚本（纯标准库，可复现）
├── existing-job_python-auto-test-engineer/      # 既有岗位
│   ├── input/jd_source.json                     # 输入：原始 JD（zhaopin，含 jd_text 原文）
│   └── output/job_ability_graph.json            # 输出：能力图谱子图（含证据引文）
└── new-job_ai-agent-security-evaluator/         # 新岗位
    ├── input/emerging_role.json                 # 输入：新岗位候选（职责/必需技能/证据 id）
    ├── input/evidence_sample.json               # 输入：证据原文样例（岗位数据源出处）
    └── output/
        ├── kg_link_delta.json                   # 输出：图谱增量提案（trend_kg_delta_v1）
        └── ability_edges_proposal.json          # 输出：新岗位能力边视图（合并后进演化图谱）
```

## 三、数据血缘（输入 → 系统处理 → 输出）

### 1）既有岗位：python自动化测试工程师（智联招聘，job_id 40857992907）

1. 原始数据源：`data/outputs/jd_raw.jsonl`（智联 zhaopin 字段：title/company/location/salary/experience/education + `jd_text` 原文）
2. 结构化解析/标注：`jd-parser` + LSKT 实体标注（产出 `data/small_raw_200_lskt_tech_v2/sentence_annotations.jsonl`，每条证据可追溯到 JD 原句与字符区间）
3. 图谱构建：岗位/能力/证据三元组写入 `data/small_raw_200_lskt_tech_v2/graph_nodes.jsonl` + `graph_edges.jsonl`
4. 入库：`scripts/import_prebuilt_kg.py` → Neo4j 快照 **kg_prebuilt_v2**（3736 节点 / 11268 边）；系统内 `GET /api/v1/knowledge-graphs/kg_prebuilt_v2` 可查
5. **本目录输出**：按“岗位 → 技术/技能/知识 → 证据”两跳抽取该岗位子图（能力节点为全图共享，故证据仅保留本 JD `jd_40857992907` 的记录），并附证据引文

> 该岗位能力图谱概要：技术（Python、C/C++、Linux、Windows、Oracle、MySQL、SQL Server、TDSQL、GaussDB、TiDB、Java）、技能（接口自动化测试、UI自动化测试、软件测试 等）、知识（金融知识、操作系统、网络基础知识），全部边带证据原文支撑。

### 2）新岗位：AI Agent安全评测工程师（趋势分析组件产出）

1. 数据源：公开招聘文本 + 政策/报告外部文档 → 证据库 `jobtrend-team-delivery-2026-08-09/component/evidence.jsonl`
2. 离线分析（`trend_discovery` 组件）：多源聚合 → 新岗位识别 → `emerging_roles.jsonl`（职责 + 5 项必需技能 + 25 条证据）
3. 图谱增量提案：`component/kg_link_delta.jsonl`（对本岗位 8 条操作：1 条 `propose_node` 新增角色节点 + 7 条 `propose_edge` 指向 红队测试 / RAG / Agent / LLM评测 / Python / 提示注入测试 / MCP 等能力）
4. 人工审核（趋势页「新岗位发现与能力演化」）→ 通过后由 `scripts/merge_kg_delta.py` 合并写入 Neo4j，生成演化快照 **kg_evolved_v1**
5. **本目录输出**：增量提案精简视图 + 新岗位“能力边”提案视图（含每条边的证据数）

## 四、字段说明（简要）

- `jd_source.json`：`job_id / job_title / company_name / industry / location / salary_* / experience / education / jd_text / responsibilities / requirements`（智联原始字段）
- `job_ability_graph.json`：`graph.nodes[]`（`id/label/label_cn/name/properties`）、`graph.edges[]`（`source/target/relation_type/evidence_ids/properties{role,confidence,surface}`）、`summary`（统计与证据引文）
- `emerging_role.json`：`role_id / canonical_title / aliases / core_responsibilities / required_skills[]`（每个技能含 `evidence_ids`）
- `evidence_sample.json`：证据原文样例（对应 `required_skills[*].evidence_ids`）
- `kg_link_delta.json`：`delta_id / operation(propose_node|propose_edge) / source_id / target_id / relation_type / resolution_status / evidence_count`
- `ability_edges_proposal.json`：`role` + `ability_edges[]`（source→target→能力名，含证据数）

## 五、复现

```powershell
cd job-ability-graph
# 任一可用 Python 3.10+（本项目可用 backend\venv\Scripts\python.exe）
python submission-testdata/tools/generate_testdata.py
```

输出会覆盖写回 `submission-testdata/`（幂等，输入源不可变）。

## 六、与在线系统一致性（可选验证）

部署后（docker compose / 本机运行）可核对：

```bash
# 既有岗位所属全图快照（Neo4j/SQLite 双端一致）
curl http://127.0.0.1:8002/api/v1/knowledge-graphs/kg_prebuilt_v2
# 图谱多跳检索（含 job:40857992907 等岗位节点）
curl -X POST "http://127.0.0.1:8002/api/v1/graph-retrievals?graph_id=kg_prebuilt_v2" \
  -H "Content-Type: application/json" \
  -d '{"query":"python","seed_entity_ids":[],"relation_types":[]}'
# 新岗位（趋势组件只读接口，Docker 部署已内置组件产物）
curl http://127.0.0.1:8002/api/v1/trends/emerging-roles
```

> 单元测试覆盖见仓库 `tests/`；本测试数据同时被用于图谱导入/检索/合并链路的冒烟验证。
