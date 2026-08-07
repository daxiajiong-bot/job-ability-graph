# 岗位能力图谱系统 — 启动指南

> **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph

## 快速开始（30 秒启动）

```bash
# 1. 启动后端（Mock 模式，无需 Ollama）
cd job-ability-graph
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 2. 新终端启动前端
cd job-ability-graph/frontend
npm run dev

# 3. 浏览器打开 http://localhost:5173
```

**启用 AI 画像生成（需要 Ollama）：**

```bash
# 安装 Ollama 后下载模型
ollama pull qwen2.5:7b

# 启动后端时设置环境变量
$env:LLM_BACKEND="ollama"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 项目结构

```
job-ability-graph/
├── backend/              # 后端服务 (FastAPI)
├── frontend/             # 前端界面 (React + Vite)
├── data/                 # 数据文件
│   ├── small-raw/        # 原始 JD 数据
│   └── app.db            # SQLite 数据库
├── jd-parser/            # JD 解析器
├── jdmatch-deployment/   # 模型部署配置
├── algorithms/           # 算法实现
├── scripts/              # 工具脚本
├── tests/                # 测试用例
├── docs/                 # 项目文档
└── requirements.txt      # Python 依赖
```

> ⚠️ **注意：** 大型模型文件 (`*.safetensors`) 已从 Git 仓库中排除（超过 GitHub 2GB 限制）。如需使用 AI 模型功能，请单独下载。

---

## 环境要求

| 组件    | 版本要求                         |
| ------- | -------------------------------- |
| Python  | 3.10+                            |
| Node.js | 18+                              |
| npm     | 9+                               |
| Ollama  | 最新版（可选，用于 AI 画像生成） |

---

## 一、后端启动

### 1. 安装依赖

```bash
cd job-ability-graph
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

复制环境变量模板，按需修改：

```bash
cp .env.example .env
```

默认即可使用的配置（无需修改）：

| 变量              | 默认值          | 说明                                                         |
| ----------------- | --------------- | ------------------------------------------------------------ |
| `DB_BACKEND`    | `sqlite`      | 数据库后端，`sqlite`(持久化) 或 `memory`(内存，重启丢失) |
| `DB_PATH`       | `data/app.db` | SQLite 数据库文件路径                                        |
| `LLM_BACKEND`   | `mock`        | 大模型后端，`mock`(默认) 或 `ollama`                     |
| `GRAPH_BACKEND` | `mock`        | 图数据库后端，`mock`(默认) 或 `neo4j`                    |

### 3. 启动后端服务

#### 模式 A：Mock 模式（默认，无需 Ollama）

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

此模式下画像生成功能返回空数据，仅用于开发调试。

#### 模式 B：Ollama 模式（AI 画像生成）

**前置条件：**

1. 安装 Ollama：https://ollama.com/download/windows
2. 下载模型：

```bash
ollama pull qwen2.5:7b
```

3. 启动后端（二选一）：

**方式一：命令行设置环境变量**

```bash
# Windows PowerShell
$env:LLM_BACKEND="ollama"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# Windows CMD
set LLM_BACKEND=ollama
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# Linux / macOS
LLM_BACKEND=ollama python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

**方式二：修改 `.env` 文件**

将 `.env` 中的：

```
LLM_BACKEND=mock
```

改为：

```
LLM_BACKEND=ollama
```

然后正常启动：

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

> ⚠️ **注意：** `.env` 文件需要应用主动加载才能生效。如果修改 `.env` 后不生效，请使用方式一。

首次启动时，系统会自动：

1. 创建 SQLite 数据库文件（`data/app.db`）
2. 建表（users / documents / profiles）
3. 从 `data/small-raw/jd_raw.jsonl` 导入 **10515 条** 初始 JD 数据

看到类似日志表示成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
Seeded 10515 initial JD records from .../data/small-raw/jd_raw.jsonl
```

### 4. 验证后端

```bash
# 健康检查（会显示数据库中的文档数量）
curl http://127.0.0.1:8000/health

# 查看 API 文档
# 浏览器打开 http://127.0.0.1:8000/docs

# 查看系统 JD 列表（需要带 X-User-ID 头）
curl -H "X-User-ID: test_user" "http://127.0.0.1:8000/api/v1/documents?document_type=jd&limit=5"
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

默认运行在 `http://localhost:5173`，Vite 会自动将 `/api` 请求代理到后端 `http://127.0.0.1:8000`。

### 3. 访问前端

浏览器打开 `http://localhost:5173`，主要页面：

| 路径          | 功能                                  |
| ------------- | ------------------------------------- |
| `/`         | 仪表盘概览                            |
| `/jd`       | JD 管理（查看/上传 JD，生成岗位画像） |
| `/resume`   | 简历管理（上传简历，生成候选人画像）  |
| `/match`    | 人岗匹配                              |
| `/history`  | 匹配历史                              |
| `/graph`    | 知识图谱                              |
| `/settings` | 系统设置                              |

---

## 三、完整启动流程（一键）

### Windows（Mock 模式）

```bash
# 终端 1：启动后端
cd job-ability-graph
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2：启动前端
cd job-ability-graph/frontend
npm run dev
```

### Windows（Ollama 模式，支持 AI 画像生成）

```bash
# 终端 1：启动后端
cd job-ability-graph
$env:LLM_BACKEND="ollama"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2：启动前端
cd job-ability-graph/frontend
npm run dev
```

### macOS / Linux

```bash
# 终端 1：启动后端
cd job-ability-graph
LLM_BACKEND=ollama python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：启动前端
cd job-ability-graph/frontend
npm run dev
```

---

## 四、数据库说明

### 存储结构

数据库文件位于 `data/app.db`（SQLite 格式），包含 3 张表：

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│   users     │     │   documents      │     │  profiles    │
├─────────────┤     ├──────────────────┤     ├──────────────┤
│ user_id (PK)│◄────│ user_id (FK)     │◄────│ user_id (FK) │
│ created_at  │     │ id (PK)          │────►│ document_id  │
│ last_active │     │ document_type    │     │ profile_type │
└─────────────┘     │ text             │     │ state        │
                    │ title            │     │ attributes   │
                    │ company_name     │     │ evidence     │
                    │ skills           │     │ ...          │
                    │ ...              │     └──────────────┘
                    └──────────────────┘
```

### 数据隔离规则

- **系统数据**（`user_id = 'system'`）：10515 条初始 JD，所有用户可见
- **用户数据**（`user_id = 用户UUID`）：用户自己上传的 JD/简历，仅自己可见
- **列表查询**自动合并：`WHERE (user_id = 'system' OR user_id = :当前用户)`

### 用户标识

- 首次访问时，前端自动生成 UUID 并存入 localStorage
- 每个请求自动携带 `X-User-ID` 请求头
- 后端自动创建用户记录

### 数据库管理

```bash
# 直接查看数据库内容
sqlite3 data/app.db

# 常用 SQL
SELECT COUNT(*) FROM documents WHERE user_id = 'system';  -- 系统 JD 数量
SELECT COUNT(*) FROM documents WHERE user_id != 'system';  -- 用户上传数量
SELECT COUNT(*) FROM users;  -- 用户数量

# 查看某用户的所有 JD
SELECT title, company_name, location, salary_range
FROM documents
WHERE document_type = 'jd' AND (user_id = 'system' OR user_id = 'xxx')
LIMIT 20;
```

### 切换数据库模式

在 `.env` 中设置：

```bash
# 使用 SQLite（默认，持久化）
DB_BACKEND=sqlite
DB_PATH=data/app.db

# 使用内存（重启丢失，适合测试）
DB_BACKEND=memory
```

---

## 五、测试

```bash
cd job-ability-graph
python -m pytest tests/ -v
```

测试默认使用 `DB_BACKEND=memory`（内存模式），不会影响生产数据库。

---

## 六、常见问题

| 问题                                             | 解决方案                                                           |
| ------------------------------------------------ | ------------------------------------------------------------------ |
| 后端启动报`No module named 'backend'`          | 确保在`job-ability-graph` 根目录下运行                           |
| 前端启动后页面空白                               | 确保后端已启动，检查`http://127.0.0.1:8000/health`               |
| JD 页面没有数据                                  | 检查`data/small-raw/jd_raw.jsonl` 是否存在，重启后端触发种子加载 |
| 数据库被锁定                                     | Windows 下确保只有一个后端进程在运行                               |
| `sqlite3.OperationalError: database is locked` | 关闭所有连接后重启后端                                             |
| 切换到内存模式后数据消失                         | 这是预期行为，内存模式不持久化                                     |
| 画像生成返回空数据 /`not_implemented`          | 检查`LLM_BACKEND` 是否设为 `ollama`，Ollama 服务是否运行中     |
| 画像生成超时                                     | 首次调用模型需加载到内存，等待 30-60 秒属正常                      |
| `ollama: command not found`                    | Ollama 未安装或未加入 PATH，重新安装后重启终端                     |

---

## 七、常见问题（续）

| 问题 | 解决方案 |
|------|----------|
| Git 推送失败：`Size must be less than or equal to 2147483648` | 大型模型文件已排除，使用 `git pull` 拉取最新代码 |
| 需要使用 AI 模型功能 | 单独下载 `Qwen3-Embedding-4B` 模型文件到 `jdmatch-deployment-qwen3-4b-v1/Qwen3-Embedding-4B/` 目录 |
| Ollama 响应超时 | 检查模型是否已下载：`ollama list`，或尝试更小的模型：`ollama pull qwen2.5:3b` |

---

## 八、验证 Ollama 配置

启动后端后，访问以下接口确认 LLM 已启用：

```bash
curl http://127.0.0.1:8000/api/v1/capabilities
```

正确配置应返回：

```json
{
  "structured_extraction": { "implementation": "ollama", "state": "available" },
  "skill_normalization": { "implementation": "lightweight", "state": "available" },
  "profile_builder": { "implementation": "llm_profile_builder", "state": "available" }
}
```

如果仍显示 `mock`，说明环境变量未生效，请使用命令行方式设置：

```powershell
$env:LLM_BACKEND="ollama"
```

然后重启后端。

---

## 九、开发指南

### 分支说明

- `main` - 主分支，稳定版本
- `dev` - 开发分支
- `feature/*` - 功能分支
- `bugfix/*` - 修复分支

### 提交规范

```bash
# 格式：<type>(<scope>): <subject>
# 示例：
git commit -m "feat(backend): 添加用户认证功能"
git commit -m "fix(frontend): 修复登录页面样式问题"
git commit -m "docs(readme): 更新项目文档"
```

### 代码规范

- **后端：** 遵循 PEP 8，使用 `ruff` 格式化
- **前端：** 遵循 ESLint 规则，使用 Prettier 格式化

---

## 十、更新日志

### 2026-08-07
- ✅ 初始化项目并上传到 GitHub
- ✅ 排除大型模型文件（超过 GitHub 2GB 限制）
- ✅ 排除 HTML 临时数据文件
- ✅ 更新项目文档

---

## 十一、相关资源

- **GitHub 仓库：** https://github.com/daxiajiong-bot/job-ability-graph
- **FastAPI 文档：** https://fastapi.tiangolo.com/
- **React 文档：** https://react.dev/
- **Ollama 官网：** https://ollama.com/
- **SQLite 文档：** https://www.sqlite.org/docs.html

---

## 十二、联系方式

如有问题或建议，请通过以下方式联系：

- **GitHub Issues：** https://github.com/daxiajiong-bot/job-ability-graph/issues
- **邮箱：** [待补充]

---

**最后更新：** 2026-08-07
