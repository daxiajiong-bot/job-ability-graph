# job-ability-graph 部署指南（容器化）

一键把「岗位能力图谱系统」以容器方式跑起来：**Neo4j（图谱）+ Ollama（自带 LLM）+ FastAPI 后端 + React/nginx 前端**。同时提供无需 Docker 的 Windows 本机启动脚本。

```
deploy/
├── docker-compose.yml          # 主编排：neo4j / ollama / ollama-pull / kg-init / backend / frontend
├── docker-compose.gpu.yml      # （可选）叠加文件：把 Ollama 调度到 NVIDIA GPU
├── Dockerfile.backend          # 后端镜像（FastAPI + uvicorn）
├── Dockerfile.frontend         # 前端镜像（Vite 构建 -> nginx 静态托管 + /api 反代）
├── nginx.conf                  # 前端容器 nginx 配置
├── docker-entrypoint.sh        # 后端容器首启脚本：向数据卷灌入图谱/ESCO/示例 JD fixtures
├── requirements.backend.txt    # 后端容器 Python 依赖
├── .env.docker                 # 环境变量模板（复制为 .env）
├── local-run.ps1               # 无 Docker：Windows 本机生产模式一键启动
├── serve-dist.mjs              # 无 Docker：前端静态服务 + /api 反代（node，零依赖）
└── README.md                   # 本文档
```

仓库根目录的 `.dockerignore` 会把 venv / node_modules / .git / 模型权重 / 非运行时大文件
从构建上下文中剔除（后端镜像里只拷 代码 + fixtures + JobTrend 组件 ≈ 几十 MB）。

---

## 一、Docker 部署（推荐，评审/服务器环境）

### 1. 前置条件

| 组件 | 要求 |
|---|---|
| Docker | 20.10+（Compose v2 插件） |
| 内存 | ≥ 8 GB（Neo4j 1.5G 堆 + Python + Ollama 推理） |
| 网络 | 首次运行需联网拉取镜像与 `qwen2.5:7b`（~4.7GB） |
| GPU（可选） | NVIDIA 驱动 + nvidia-container-toolkit（见“GPU 加速”） |

> 若宿主机已在跑本仓库的便携版 Neo4j（7687）或 Ollama（11434），先停掉它们，
> 或改 `deploy/.env` 里的 `NEO4J_HTTP_PORT/NEO4J_BOLT_PORT/WEB_PORT/BACKEND_PORT`。
> Ollama 容器默认不向宿主机发布端口，避免与宿主机 Ollama 冲突。

### 2. 准备配置

```powershell
cd job-ability-graph\deploy
copy .env.docker .env        # 按需修改密码/端口/模型名
```

### 3. 构建并启动

```powershell
docker compose up -d --build
```

首次启动会自动执行：

1. 拉起 `neo4j` 并等待健康（`cypher-shell` 探测）；
2. `ollama-pull` 下载 `qwen2.5:7b`（可 `docker compose logs -f ollama-pull` 观察）；
3. `kg-init` 把 `data/small_raw_200_lskt_tech_v2`（3736 节点/11268 边）导入 Neo4j 快照 `kg_prebuilt_v2`；
4. `backend` 就绪：把 fixtures 复制进 `appdata` 数据卷并自动建库、注册快照、写入 100 条示例 JD；
5. `frontend` 就绪后访问 **http://localhost:8080**。

常用命令：

```powershell
docker compose ps                          # 各服务状态
docker compose logs -f backend             # 后端日志
docker compose logs -f ollama-pull         # 大模型下载进度
docker compose run --rm kg-init            # 手动重导图谱（幂等，可重复执行）
docker compose down                        # 停止（不加 -v 保留数据卷）
docker compose down -v                     # 停止并删除全部数据卷（重置）
```

### 4. GPU 加速（可选）

有 NVIDIA GPU 时给 Ollama 上 GPU：

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

没有 GPU 也能跑（CPU 推理较慢，属正常）。

### 5. 验证

```powershell
# 浏览器
# 前端：  http://localhost:8080
# API：   http://localhost:8002/docs
# Neo4j： http://localhost:7474   (neo4j / <deploy\.env 的 NEO4J_PASSWORD>)

# 命令行
curl http://localhost:8002/api/v1/capabilities   # knowledge_graph/graph_rag 应为 neo4j
```

页面里依次检查：仪表盘 → JD 管理（生成岗位画像，需模型已拉好）→ 知识图谱
（节点/边有数据、节点搜索可用）→ 人岗匹配 → 智能推荐（`meta.recall` 此时为 `sql`，
因为容器默认关闭语义嵌入，不影响其它功能）。

---

## 二、关键说明

### 数据与持久化

| 命名卷 | 内容 |
|---|---|
| `appdata` | 后端 `/app/data`：SQLite（`app.db`）、图谱 fixtures、ESCO 索引、上传/画像产物 |
| `neo4j-*` | Neo4j 数据/日志/导入/插件 |
| `ollama-store` | Ollama 模型权重 |

首启流程：`backend` 的 `docker-entrypoint.sh` 看到卷里没有 `.seeded` 标记时，把
镜像内 `/.fixtures`（`small_raw_200_lskt_tech_v2`、`esco`、`jd_raw_100.jsonl`）
复制进卷，然后 uvicorn 启动并自动建表/导入。之后重启都是秒级 no-op。

> 容器内自动入库的是 100 条示例 JD（后端启动脚本固定读 `jd_raw_100.jsonl`）。
> 若要全量 10515 条，可用数据卷预置方案：先 `docker compose up -d neo4j backend` 一次，
> 然后把仓库 `data/small-raw/jd_raw.jsonl` 拷进卷内对应路径并重启一个临时容器
> 执行 `load_initial_jds`，或直接改 `backend/app/main.py` 的 seed 文件名后重新构建。

### 环境变量（deploy/.env）

见 `.env.docker` 内注释。最常用：

| 变量 | 默认 | 说明 |
|---|---|---|
| `NEO4J_VERSION` | `2026.05.0` | 镜像 tag；官方仓库拉不到就换 `5.26.0`（Cypher 兼容） |
| `NEO4J_PASSWORD` | `jobgraph_neo4j_2026` | Neo4j 密码，生产环境务必修改 |
| `LLM_MODEL` | `qwen2.5:7b` | 拉取与调用使用的模型（`ollama-pull` 与其保持一致） |
| `LLM_BACKEND` | `ollama` | 改为 `mock` 可完全不依赖模型跑通演示 |
| `EMBEDDING_BACKEND` | `off` | 语义嵌入默认关（见下） |
| `JWT_SECRET_KEY` | 开发默认值 | 生产环境务必修改 |
| `BACKEND_PORT` / `WEB_PORT` | `8002` / `8080` | 宿主机端口 |

### 语义嵌入（Qwen3-Embedding-4B）为什么默认关闭

微调模型在 `jdmatch-deployment-qwen3-4b-v1/`（约 8GB）+ CUDA torch，体积大、需要 GPU。
需要语义召回（`auto-match` 的 `meta.recall=hybrid`）时：

1. 在 `docker-compose.gpu.yml` 里给 `backend` 服务追加同样的 GPU `deploy` 块；
2. 给 `backend` 服务挂载模型目录（`- /absolute/path/to/jdmatch-deployment-qwen3-4b-v1:/models:ro`）
   并设 `EMBEDDING_BACKEND=local`、`EMBEDDING_MODEL_DIR=/models/Qwen3-Embedding-4B`；
3. 镜像需加装 `torch sentence-transformers peft accelerate bitsandbytes`
   （把这几个包追加进 `requirements.backend.txt` 后重建，或提供独立 GPU 镜像）。

不需要该能力时保持 `off`，其余功能不受影响（推荐召回自动降级为 SQL 重叠）。

### OCR（PaddleOCR）

容器镜像**未内置** PaddleOCR（镜像瘦身）。上传图片/PDF 做 OCR 的接口在容器中会不可用；
文档上传走文本/RAG 等其它流程不受影响。需要 OCR 时在 `requirements.backend.txt` 追加
`paddlepaddle paddleocr` 并重建（体积增加较大）。

### JobTrend 增量更新 / 图谱演化

`/api/v1/trends*` 接口直接读取镜像内 `jobtrend-team-delivery-2026-08-09/component/`
的离线产物（已随后端镜像打包）；「审核通过并写入图谱」会经 `backend` 直写 Neo4j。

---

## 三、无 Docker：Windows 本机生产模式

适合没有 Docker 的机器（含本机演示）：

```powershell
cd job-ability-graph
powershell -ExecutionPolicy Bypass -File deploy\local-run.ps1
```

脚本会：

1. 检测/启动便携 Neo4j（`scripts\neo4j_local.ps1`，需 `D:\neo4j`）；
2. 用 `backend\venv` 的 Python 起 uvicorn（127.0.0.1:8002，读取仓库根 `.env`）；
3. 构建 `frontend\dist` 并用内置 node 静态服务器托管 + `/api` 反代
   （http://127.0.0.1:5173）；
4. 按 Enter 退出并清理进程。

其它参数：`-SkipBuild`（复用已构建 dist）、`-WebPort`/`-BackendPort`、`-NoOllama`。

前置：仓库根有 `.env`（GRAPH_BACKEND=neo4j、LLM_BACKEND=ollama 等）、已安装 Node 18+，
如需 LLM 功能则宿主机 Ollama 已拉 `qwen2.5:7b`。

---

## 四、常见问题

| 现象 | 处理 |
|---|---|
| `docker compose up` 拉不到 `neo4j:2026.05.0` | `.env` 里改 `NEO4J_VERSION=5.26.0` 后重试 |
| 端口冲突起不来 | 宿主机先停便携 Neo4j / Ollama / 旧后端；或改 `.env` 端口 |
| 图谱检索空/500 | Neo4j 未导入：`docker compose run --rm kg-init`；确认 `GRAPH_BACKEND=neo4j` |
| 画像/报告报模型错误 | `docker compose logs -f ollama-pull` 确认模型已拉完；CPU 推理慢请耐心或开 GPU |
| 知识图谱页空白 | 等 `backend` healthy 后强刷（Ctrl+F5） |
| `kg-init` 每次 `up` 都重导 | 属预期（MERGE 幂等）；想完全跳过可注释掉 kg-init 并把 backend 的 depends_on 改为 neo4j |
| 数据库锁 | 后端只允许单实例，勿同时映射多副本 |
| 想重置环境 | `docker compose down -v` 后重新 `up -d --build` |

---

*构建产物交付提示：把整个 `job-ability-graph/`（含 `deploy/` 与根 `.dockerignore`）拷到
目标机器即可构建；无需携带 `backend/venv`、`frontend/node_modules`、`data/` 大文件
与 `jdmatch-deployment-qwen3-4b-v1` 等（`.dockerignore` 已排除）。*
