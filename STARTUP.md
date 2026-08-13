# 岗位能力图谱系统 — 启动指南

> **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph

## 快速开始

```bash
# 1. 启动后端
cd job-ability-graph
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 2. 新终端启动前端
cd job-ability-graph/frontend
npm run dev

# 3. 浏览器打开 http://localhost:5173
```

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
│       └── infrastructure/       # 适配器（LLM、Neo4j、SQLite）
├── frontend/                     # 前端界面 (React 19 + Vite)
├── data/                         # 数据文件
│   ├── app.db                    # SQLite 数据库（~66MB）
│   ├── small-raw/                # 原始 JD 数据（10515 条）
│   ├── small_raw_200_lskt_tech_v2/  # 预构建知识图谱
│   └── rag/                      # RAG 检索数据
├── jd-parser/                    # JD 结构化解析管线
├── jdmatch-deployment-qwen3-4b-v1/  # Qwen3-Embedding 微调
├── JobCloud/                     # 独立 3D 可视化应用
├── tests/                        # 测试用例
├── docs/                         # 项目文档
├── .env                          # 环境变量配置
└── requirements.txt              # Python 依赖
```

---

## 环境要求

| 组件    | 版本要求 | 说明                              |
| ------- | -------- | --------------------------------- |
| Python  | 3.10+    | 后端运行                          |
| Node.js | 18+      | 前端构建                          |
| Ollama  | 最新版   | 可选，用于 AI 画像生成 + 学习建议 |

---

## 一、后端启动

### 1. 安装依赖

```bash
cd job-ability-graph
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件，核心配置项：

| 变量                     | 默认值         | 说明                                                    |
| ------------------------ | -------------- | ------------------------------------------------------- |
| `DB_BACKEND`           | `sqlite`     | 数据库：`sqlite`（持久化）或 `memory`（重启丢失）   |
| `LLM_BACKEND`          | `ollama`     | 大模型：`mock`（无 AI）或 `ollama`（需安装 Ollama） |
| `GRAPH_BACKEND`        | `mock`       | 图数据库：`mock` 或 `neo4j`                         |
| `LLM_MODEL`            | `qwen2.5:7b` | Ollama 模型名                                           |
| `DATA_GOVERNANCE_ROOT` | `data`       | 数据目录                                                |

### 3. 启动后端服务

#### 模式 A：Mock 模式（无需 Ollama）

```bash
# 临时设置环境变量
$env:LLM_BACKEND="mock"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
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
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

> ⚠️ **注意：** 不要使用 `--reload` 参数，否则 `.env` 配置可能不被正确加载。

首次启动时，系统会自动：

1. 创建 SQLite 数据库（`data/app.db`）
2. 建表（users / documents / profiles / matches / reports）
3. 导入 **10515 条**初始 JD 数据
4. 加载预构建知识图谱（3736 节点，11268 边）

看到类似日志表示成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
Seeded 10515 initial JD records from .../data/small-raw/jd_raw.jsonl
```

### 4. 验证后端

```bash
# 健康检查
curl http://127.0.0.1:8000/health

# 查看系统能力（确认 LLM 和 Graph-RAG 状态）
curl http://127.0.0.1:8000/api/v1/capabilities

# API 文档
# 浏览器打开 http://127.0.0.1:8000/docs
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

| 路径          | 功能                                  |
| ------------- | ------------------------------------- |
| `/`         | 仪表盘概览                            |
| `/jd`       | JD 管理（查看/上传 JD，生成岗位画像） |
| `/resume`   | 简历管理（上传简历，生成候选人画像）  |
| `/match`    | 人岗匹配                              |
| `/history`  | 匹配历史                              |
| `/graph`    | 3D 星图可视化                         |
| `/settings` | 系统设置                              |

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

---

## 六、测试

```bash
cd job-ability-graph
python -m pytest tests/ -v
```

测试默认使用 `DB_BACKEND=memory`，不影响生产数据库。

---

## 七、常见问题

| 问题                            | 解决方案                                             |
| ------------------------------- | ---------------------------------------------------- |
| `No module named 'backend'`   | 在`job-ability-graph` 根目录下运行                 |
| 前端页面空白                    | 确保后端已启动，访问`http://127.0.0.1:8000/health` |
| JD 页面没有数据                 | 检查`data/small-raw/jd_raw.jsonl` 是否存在         |
| 数据库被锁定                    | 确保只有一个后端进程运行                             |
| 画像返回`not_implemented`     | 检查`LLM_BACKEND` 是否设为 `ollama`              |
| 学习建议显示 Mock               | 需要`LLM_BACKEND=ollama` 且 Ollama 运行中          |
| 学习建议显示 LLM 而非 Graph-RAG | 重启后端（不要用`--reload`）                       |
| Ollama 响应超时                 | 首次加载模型需 30-60 秒，属正常                      |
| `ollama: command not found`   | 重新安装 Ollama 并重启终端                           |

---

## 八、技术栈

| 层        | 技术                            |
| --------- | ------------------------------- |
| 后端框架  | Python 3.10+, FastAPI, Uvicorn  |
| 数据库    | SQLite（默认）/ Neo4j（可选）   |
| 大模型    | Ollama + qwen2.5:7b（本地推理） |
| 知识图谱  | 预构建 JSONL + 内存检索         |
| RAG       | 关键词检索（DataGovernanceRag） |
| 前端框架  | React 19, Vite 8, Ant Design 6  |
| 3D 可视化 | Three.js, @react-three/fiber    |
| 图表      | ECharts                         |
| 状态管理  | Zustand                         |
| ML 训练   | Qwen3-Embedding-4B LoRA 微调    |

---

## 九、相关资源

- **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph
- **FastAPI 文档：** https://fastapi.tiangolo.com/
- **React 文档：** https://react.dev/
- **Ollama 官网：** https://ollama.com/
- **Ant Design 文档：** https://ant.design/

---

**最后更新：** 2026-08-10
