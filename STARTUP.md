# 岗位能力图谱系统 — 启动指南

> **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph

## 快速开始

> 推荐使用 `backend/venv`（已装好 CUDA torch + 嵌入模型依赖）；前端代理已指向 `8002`。

```bash
# 0. 启动 Neo4j（知识图谱后端，便携式部署，无需 Docker）
powershell -ExecutionPolicy Bypass -File scripts/neo4j_local.ps1 start

# 1. 启动后端（在 job-ability-graph 根目录，使用 backend/venv）
cd job-ability-graph
.\backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002

# 2. 新终端启动前端
cd job-ability-graph/frontend
npm run dev

# 3. 浏览器打开 http://localhost:5173
```

> ⚠️ **只保留一个后端进程**：前端 Vite 代理固定指向 `8002`，不要在 `8000` 另起旧实例，否则页面会连到错误配置。

---

## 项目结构

```
job-ability-graph/
├── backend/                      # 后端服务 (FastAPI)
│   └── app/
│       ├── api/v1/               # API 路由
│       ├── application/use_cases/ # 业务门面
│       ├── data_governance/      # 数据治理 + RAG
│       ├── domain/               # 领域实体
│       └── infrastructure/       # 适配器（LLM、Neo4j、SQLite、嵌入）
├── frontend/                     # 前端界面 (React 19 + Vite)
├── data/                         # 数据文件
│   ├── app.db                    # SQLite 数据库（~66MB）
│   ├── small-raw/                # 原始 JD 数据（10515 条）
│   ├── small_raw_200_lskt_tech_v2/  # 预构建知识图谱（已导入 Neo4j）
│   ├── embeddings/               # Qwen3-Embedding 向量索引（vectors.npy + ids.json）
│   └── rag/                      # RAG 检索数据
├── jd-parser/                    # JD 结构化解析管线
├── jdmatch-deployment-qwen3-4b-v1/  # Qwen3-Embedding 微调（模型 + LoRA）
├── jobtrend-team-delivery-2026-08-09/ # 趋势/新岗位发现组件（含 kg_link_delta）
├── scripts/
│   ├── neo4j_local.ps1           # 便携 Neo4j 启停（Windows，免 Docker）
│   ├── import_prebuilt_kg.py     # 预构建图谱导入 Neo4j
│   ├── merge_kg_delta.py         # kg_link_delta 增量合并（图谱自我进化）
│   └── build_embedding_index.py  # 构建语义向量索引
├── JobCloud/                     # 独立 3D 可视化应用
├── tests/                        # 测试用例
├── docs/                         # 项目文档
├── .env                          # 环境变量配置
└── requirements.txt              # Python 依赖
```

> 便携式 Neo4j 部署在 `D:\neo4j\`（JDK 21 + Neo4j Community 2026.05），属系统级运行时，不在仓库内。

---

## 环境要求

| 组件    | 版本要求 | 说明                                                      |
| ------- | -------- | --------------------------------------------------------- |
| Python  | 3.10+    | 后端运行（本机推荐`backend/venv`，已含嵌入依赖）        |
| Node.js | 18+      | 前端构建                                                  |
| Ollama  | 最新版   | 画像生成 / LLM 匹配 / 报告 / 学习建议（qwen2.5:7b）       |
| JDK     | 21       | Neo4j 2026 必需（便携版已装在`D:\neo4j\jdk-21.0.12+8`） |
| GPU     | 可选     | 语义嵌入加速（本机 RTX 4060，8-bit 量化约 4GB 显存）      |

---

## 一、后端启动

### 1. 安装依赖

```bash
cd job-ability-graph
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件，核心配置项：

| 变量                               | 默认值                                              | 说明                                                            |
| ---------------------------------- | --------------------------------------------------- | --------------------------------------------------------------- |
| `DB_BACKEND`                     | `sqlite`                                          | 数据库：`sqlite`（持久化）或 `memory`（重启丢失）           |
| `LLM_BACKEND`                    | `ollama`                                          | 大模型：`mock`（无 AI）或 `ollama`（需安装 Ollama）         |
| `GRAPH_BACKEND`                  | `neo4j`                                           | 图数据库：`neo4j`（推荐）或 `mock`（内存 JSONL）            |
| `NEO4J_URI` / `NEO4J_PASSWORD` | `bolt://localhost:7687` / `jobgraph_neo4j_2026` | Neo4j 连接参数，与`neo4j_local.ps1` 一致                      |
| `EMBEDDING_BACKEND`              | `local`                                           | 语义召回：`local`（Qwen3-Embedding-4B）或 `off`             |
| `EMBEDDING_QUANT`                | `8bit`                                            | 嵌入量化：`none`（需 16GB+ 显存）/ `8bit`（推荐）/ `4bit` |
| `EMBEDDING_BATCH_SIZE`           | `8`                                               | 编码批次，8GB 显存建议保持 8                                    |
| `LLM_MODEL`                      | `qwen2.5:7b`                                      | Ollama 模型名                                                   |
| `DATA_GOVERNANCE_ROOT`           | `data`                                            | 数据目录                                                        |

> 完整配置见 `.env.example`（含 NEO4J_*、OCR_*、LLM_*、EMBEDDING_* 全部选项）。

### 3. 启动后端服务

#### 模式 A：Mock 模式（无需 Ollama）

```bash
# 临时设置环境变量
$env:LLM_BACKEND="mock"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002
```

此模式下画像生成和学习建议返回模拟数据，仅用于前端开发调试。

#### 模式 B：Ollama 模式（完整功能）

**前置条件：**

1. 安装 Ollama：https://ollama.com/download/windows
2. 下载模型：

```bash
ollama pull qwen2.5:7b
```

3. 确认 `.env` 中 `LLM_BACKEND=ollama`，然后启动：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002
```

> ⚠️ **注意：** 不要使用 `--reload` 参数，否则 `.env` 配置可能不被正确加载。

首次启动时，系统会自动：

1. 创建 SQLite 数据库（`data/app.db`）
2. 建表（users / documents / profiles / matches / reports）
3. 导入 **10515 条**初始 JD 数据
4. 注册预构建知识图谱快照（`kg_prebuilt_v2`，3736 节点 / 11268 边）
5. 加载语义向量索引（`data/embeddings`，若已构建）

看到类似日志表示成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8002
Seeded 10515 initial JD records from .../data/small-raw/jd_raw.jsonl
Registered pre-built knowledge graph snapshot kg_prebuilt_v2
```

### 4. 验证后端

```bash
# 健康检查
curl http://127.0.0.1:8002/health

# 查看系统能力（确认 LLM、Neo4j、嵌入状态）
curl http://127.0.0.1:8002/api/v1/capabilities
# 期望：knowledge_graph / graph_rag = neo4j、matching = llm_matcher

# API 文档
# 浏览器打开 http://127.0.0.1:8002/docs
```

---

## 二、前端启动

### 1. 安装依赖

```bash
cd job-ability-graph/frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

默认运行在 `http://localhost:5173`，Vite 会自动将 `/api` 请求代理到后端。

### 3. 主要页面

| 路径           | 功能                                  |
| -------------- | ------------------------------------- |
| `/`          | 仪表盘概览                            |
| `/jd`        | JD 管理（查看/上传 JD，生成岗位画像） |
| `/resume`    | 简历管理（上传简历，生成候选人画像）  |
| `/match`     | 人岗匹配                              |
| `/recommend` | 智能推荐（嵌入混合召回 + LLM 打分）   |
| `/history`   | 匹配历史                              |
| `/graph`     | 知识图谱（Neo4j 真实数据，节点搜索高亮） |
| `/starmap`   | 3D 星图可视化                         |
| `/settings`  | 系统设置                              |

---

## 三、核心功能说明

### 人岗匹配 + 学习建议

完整流程：

```
上传简历 → 生成候选人画像
上传 JD（或选用系统已有 JD）→ 生成岗位画像
创建人岗匹配 → 得到匹配得分和技能差距
生成学习建议 → 基于知识图谱 RAG 的个性化建议
```

**学习建议（Graph-RAG）：** 当 `LLM_BACKEND=ollama` 时，系统会：

1. 从匹配结果中提取 top-3 差距技能
2. 在知识图谱中检索每个技能的共现技能和需求岗位
3. 从 RAG 数据中检索相关 JD 原文片段
4. 拼装上下文送入 LLM 生成个性化学习建议

前端展示三个区域：

- **技能差距分析**：每个差距技能的当前/目标水平、学习步骤
- **知识图谱分析依据**：关联技能、需求岗位、JD 真实引用
- **分阶段学习计划**：按阶段规划的学习路径

---

## 四、数据库说明

### 存储结构

数据库文件位于 `data/app.db`（SQLite），包含以下表：

| 表            | 说明                  |
| ------------- | --------------------- |
| `users`     | 用户信息              |
| `documents` | 文档（JD / 简历）     |
| `profiles`  | 画像（候选人 / 岗位） |
| `matches`   | 人岗匹配结果          |
| `reports`   | 匹配报告              |
| `tasks`     | 异步任务              |

### 数据隔离

- **系统数据**（`user_id = 'system'`）：10515 条初始 JD，所有用户可见
- **用户数据**（`user_id = 用户UUID`）：用户上传的 JD/简历，仅自己可见
- 列表查询自动合并：`WHERE (user_id = 'system' OR user_id = :当前用户)`

### 数据库管理

```bash
sqlite3 data/app.db

# 常用查询
SELECT COUNT(*) FROM documents WHERE user_id = 'system';
SELECT COUNT(*) FROM profiles;
SELECT COUNT(*) FROM matches;
```

---

## 五、知识图谱数据

### 预构建图谱

路径：`data/small_raw_200_lskt_tech_v2/`

| 文件                      | 大小  | 说明           |
| ------------------------- | ----- | -------------- |
| `graph_nodes.jsonl`     | 1.1MB | 3736 个节点    |
| `graph_edges.jsonl`     | 2.9MB | 11268 条边     |
| `jd_profiles.jsonl`     | 2.4MB | 结构化 JD 画像 |
| `resume_profiles.jsonl` | 3.5MB | 结构化简历画像 |

### 节点类型

| 标签                  | 数量 | 含义                     |
| --------------------- | ---- | ------------------------ |
| Job                   | 100  | 岗位                     |
| Technology            | 76   | 技术（Python、React 等） |
| Skill                 | 65   | 技能（自动化测试等）     |
| Knowledge             | 21   | 知识（金融知识等）       |
| TransversalCompetence | 13   | 通用能力（沟通能力等）   |
| Evidence              | 3330 | 原文证据                 |

### 边的关系

```
Job ──REQUIRES_TECHNOLOGY──→ Technology
Job ──REQUIRES_SKILL──→ Skill
Job ──REQUIRES_KNOWLEDGE──→ Knowledge
Candidate ──HAS_TECHNOLOGY──→ Technology
Candidate ──HAS_SKILL──→ Skill
Technology/Skill ──SUPPORTED_BY──→ Evidence
```

> 该图谱已导入 Neo4j（快照 `kg_prebuilt_v2`），前端 `/graph` 页面直接查询图数据库，而非内存 JSONL。

---

## 六、Neo4j 知识图谱

### 1. 启动 / 停止（便携式，免 Docker）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/neo4j_local.ps1 start     # 启动并等待就绪
powershell -ExecutionPolicy Bypass -File scripts/neo4j_local.ps1 status    # 查看 7687/7474 端口
powershell -ExecutionPolicy Bypass -File scripts/neo4j_local.ps1 stop      # 停止
powershell -ExecutionPolicy Bypass -File scripts/neo4j_local.ps1 browser   # 打印访问信息
```

- 部署位置：`D:\neo4j\neo4j-community-2026.05.0` + `D:\neo4j\jdk-21.0.12+8`
- 账号：`neo4j / jobgraph_neo4j_2026`；Browser：http://localhost:7474
- 若使用 Docker 环境，也可用仓库自带的 `docker-compose.neo4j.yml`

### 2. 预构建图谱导入

```bash
python scripts/import_prebuilt_kg.py   # 将 small_raw_200_lskt_tech_v2 导入为快照 kg_prebuilt_v2
```

### 3. 图谱增量合并（动态演化）

JobTrend 组件只产出"提案"（`kg_link_delta.jsonl`，待人工审核），合并脚本将审核通过的增量写入 Neo4j：

```bash
python scripts/merge_kg_delta.py               # 默认只合并 resolution_status=approved
python scripts/merge_kg_delta.py --force       # 演示：连 unresolved 一起合并
```

合并后生成演化快照 `kg_evolved_v1`（如 "AI Agent安全评测工程师" → REQUIRES_SKILL → 红队测试/RAG/Agent…）。

### 4. 后端接线

- `.env` 中 `GRAPH_BACKEND=neo4j` 后，`POST /knowledge-graphs` 真实写入 Neo4j，`POST /graph-retrievals` 走 Cypher 多跳检索
- 前端 `/graph` 页面：加载 `kg_prebuilt_v2`（默认按连接度取 Top-N 节点），支持分类筛选、节点搜索、力导向/环形布局切换

---

## 七、语义嵌入召回（Qwen3-Embedding-4B + LoRA）

### 1. 作用

智能推荐（`/auto-match`）使用**混合召回**：微调后的 Qwen3-Embedding-4B 做语义检索 + SQL 技能重叠召回，候选池再由 LLM 打分。响应中 `meta.recall=hybrid` 表示嵌入召回生效。

### 2. 依赖与配置

- 模型：`jdmatch-deployment-qwen3-4b-v1/Qwen3-Embedding-4B`（BF16 约 8GB）+ LoRA `best_adapter`
- 依赖安装（`backend/venv`）：`torch`（CUDA）+ `sentence-transformers` + `peft` + `accelerate` + `bitsandbytes`
- `.env`：`EMBEDDING_BACKEND=local`、`EMBEDDING_QUANT=8bit`（8GB 显存推荐；`none` 需 16GB+）

### 3. 索引构建

```bash
# 全量（10518 条，GPU 约 1.5-2.5 小时）
python scripts/build_embedding_index.py

# 指定条数（如 100，约 1 分钟）
python scripts/build_embedding_index.py --limit 100
```

产物：`data/embeddings/vectors.npy` + `ids.json` + `meta.json`。索引为空时嵌入召回自动静默降级为 SQL 召回（`recall=sql`），不影响其他功能。

### 4. 验证

```bash
# 接口级验证：创建一份简历文档，再调用智能推荐，响应 meta.recall 应为 "hybrid"
curl -X POST http://127.0.0.1:8002/api/v1/documents \
  -H "Content-Type: application/json" \
  -d '{"document_type":"resume","text":"Python 后端开发工程师，熟悉 Django、FastAPI、MySQL、Redis、Docker"}'

# 取返回的 document id 后：
curl -X POST http://127.0.0.1:8002/api/v1/auto-match \
  -H "Content-Type: application/json" \
  -d '{"document_id":"<上一步返回的id>","top_n":5}'
# 期望 meta.recall == "hybrid"（嵌入召回生效）；若为 "sql" 请先构建索引
```

---

## 八、测试

```bash
cd job-ability-graph
python -m pytest tests/ -v
```

测试默认使用 `DB_BACKEND=memory`，不影响生产数据库。

---

## 九、常见问题

| 问题                             | 解决方案                                                                         |
| -------------------------------- | -------------------------------------------------------------------------------- |
| `No module named 'backend'`    | 在`job-ability-graph` 根目录下运行                                             |
| 前端页面空白                     | 确保后端已启动，访问`http://127.0.0.1:8002/health`；Vite 代理只指向 8002       |
| 图谱页看不到数据                 | ① 确认 Neo4j 已启动（`scripts/neo4j_local.ps1 status`）② 浏览器 Ctrl+F5 强刷 |
| 图谱检索返回空                   | `GRAPH_BACKEND=neo4j` + Neo4j 运行中；先执行 `import_prebuilt_kg.py`         |
| JD 页面没有数据                  | 检查`data/small-raw/jd_raw.jsonl` 是否存在                                     |
| 数据库被锁定                     | 确保只有一个后端进程运行（不要同时在 8000/8002 各起一个）                        |
| 画像返回`not_implemented`      | 检查`LLM_BACKEND` 是否设为 `ollama`                                          |
| 学习建议显示 Mock                | 需要`LLM_BACKEND=ollama` 且 Ollama 运行中                                      |
| 学习建议显示 LLM 而非 Graph-RAG  | 重启后端（不要用`--reload`）                                                   |
| 智能推荐`recall=sql`（无嵌入） | 先跑`build_embedding_index.py` 构建索引；检查 `EMBEDDING_QUANT` 与显存       |
| 嵌入模型加载 OOM                 | `EMBEDDING_QUANT=4bit` 进一步省显存，或 `EMBEDDING_BACKEND=off` 关闭嵌入     |
| Ollama 响应超时                  | 首次加载模型需 30-60 秒，属正常                                                  |
| `ollama: command not found`    | 重新安装 Ollama 并重启终端                                                       |

---

## 十、技术栈

| 层        | 技术                                                |
| --------- | --------------------------------------------------- |
| 后端框架  | Python 3.10+, FastAPI, Uvicorn                      |
| 数据库    | SQLite（默认）/ Neo4j（知识图谱）                   |
| 大模型    | Ollama + qwen2.5:7b（本地推理）                     |
| 语义嵌入  | Qwen3-Embedding-4B + LoRA（8-bit 量化，混合召回）   |
| 知识图谱  | Neo4j 2026（Cypher 多跳检索）                       |
| RAG       | 关键词检索（DataGovernanceRag）+ Graph-RAG 学习建议 |
| 前端框架  | React 19, Vite 8, Ant Design 6                      |
| 3D 可视化 | Three.js, @react-three/fiber                        |
| 图表      | ECharts（力导向/环形图谱、雷达图）                  |
| 状态管理  | Zustand                                             |
| ML 训练   | Qwen3-Embedding-4B LoRA 微调                        |

---

## 十一、相关资源

- **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph
- **FastAPI 文档：** https://fastapi.tiangolo.com/
- **React 文档：** https://react.dev/
- **Ollama 官网：** https://ollama.com/
- **Ant Design 文档：** https://ant.design/

---

**最后更新：** 2026-08-14
