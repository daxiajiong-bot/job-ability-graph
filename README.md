# v3 Contract Skeleton

正式、版本化的岗位—能力图谱系统接口骨架。当前实现提供：

- 进程内资源管理；
- PaddleOCR 文档识别入口；
- 明确的 mock 智能能力边界；
- 可选 Neo4j 知识图谱写入与图谱路径检索；
- 文件级数据治理入口，用于为知识图谱 RAG 建立 `doc_id`、`chunk_id`、`version`、`evidence` 追溯链。

默认配置下，画像、匹配、报告等智能接口仍使用 mock，不执行打分、自由生成或爬虫；文件级数据治理链路会执行 LSKT span 抽取、ESCO 概念链接、证据绑定、图谱 JSON 产物生成和最小 RAG。设置 `GRAPH_BACKEND=neo4j` 后，`knowledge_graph` 与 `graph_rag` 会切换到 Neo4j adapter，用于后续部署岗位—技能—能力知识图谱。
设置 `LLM_BACKEND=ollama` 后，简历/JD 画像会通过本地 Ollama 模型做 `profile-extraction/v2` 结构化抽取，并把 `ResumeProfile` / `JDProfile` JSON 落盘到 `data/structured/profiles/`；模型不可用或输出不合规时会降级为 mock 并在响应 `warnings` 中说明原因。

## 启动

建议使用 Python 3.10+。项目源码使用了现代类型标注语法，系统自带旧版 Python 可能无法解析。

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

- 健康检查：`GET /health`
- OpenAPI：`/docs`
- 正式 API：`/api/v1`
- 能力状态：`GET /api/v1/capabilities`

## 数据文件治理

治理目录位于 `data/raw`、`data/staging`、`data/structured`、`data/graph`、`data/rag`、`data/audit`，能力本体索引位于 `data/esco`。上传或登记本地文件后，系统会计算 hash、管理版本、解析清洗、切块、用本地 Ollama 生成 LSKT 能力 span draft，再链接到官方 ESCO 快照索引、绑定原文 evidence、生成图谱 JSON 和 RAG chunk 索引。

LSKT 只作为能力分类字段使用，不作为完整知识图谱 schema：`K` 表示知识/理论/标准，`S` 表示可执行技能，`T` 表示通用能力，`L` 表示语言能力。每个候选 span 都必须能从原文按 `start_char/end_char` 切回，且 evidence quote 必须包含该 span；不满足证据约束的候选不会进入 structured、graph 或 rag 产物。

系统不再维护运行时手写技能词表。`ESCO_INDEX_ROOT` 默认是 `data/esco`，`ESCO_VERSION` 默认是 `v1.2.1`；如果缺少 `data/esco/index/concepts.jsonl`，数据治理服务会给出明确错误。仓库自带一个最小 ESCO 测试索引，比赛演示前建议用官方 CSV 快照重新生成：

```bash
python3 scripts/build_esco_index.py \
  --source /path/to/official-esco-csv-or-zip \
  --output-root data/esco \
  --version v1.2.1
```

上传登记并处理：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/documents/register \
  -F document_type=jd \
  -F source_system=manual \
  -F external_id=jd-001 \
  -F file=@/path/to/jd.txt

curl -X POST http://127.0.0.1:8000/api/v1/data-governance/documents/{doc_id}/process \
  -H 'Content-Type: application/json' \
  -d '{}'
```

检索并生成带证据回答：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/rag/answer \
  -H 'Content-Type: application/json' \
  -d '{"query":"Python MySQL 要求","doc_ids":["doc_xxx"],"top_k":5}'
```

本地 Ollama 用作 Chinese-SkillSpan 风格的 draft 标注器和中文 span 到 ESCO 候选的受限选择器。模型只能从召回候选 URI 中选择；无法回链原文、候选外 URI 或低置信度结果都会被保留为 `unmapped`，不会硬贴 ESCO：

```bash
export LSKT_SPAN_BACKEND=ollama
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:7b
export ESCO_INDEX_ROOT=data/esco
export ESCO_VERSION=v1.2.1
```

详细流程见 [docs/data-governance.md](docs/data-governance.md)。项目变更记录见 [docs/project-log.md](docs/project-log.md)。

## 启用 Neo4j

先复制环境变量模板并按需修改密码、端口和内存：

```bash
cp .env.example .env
```

启动本地 Neo4j：

```bash
scripts/neo4j.sh start
```

等价的原始 Docker Compose 命令是：

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

再启动后端：

```bash
export GRAPH_BACKEND=neo4j
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=jobgraph_neo4j_2026
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Neo4j Browser 地址为 `http://localhost:7474`。默认用户名是 `neo4j`，密码是 `jobgraph_neo4j_2026`。

常用管理命令：

```bash
scripts/neo4j.sh status
scripts/neo4j.sh logs
scripts/neo4j.sh shell
scripts/neo4j.sh stop
scripts/neo4j.sh reset
```

## 快速示例

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{"document_type":"resume","text":"匿名简历原文","source":{"source_system":"manual"}}'
```

响应仅返回文档元数据、长度和摘要校验值，不回显原文。服务重启后，内存资源会清空；开启 Neo4j 时，图谱节点和关系会持久化在 Neo4j 数据卷中。

OCR 上传会将图片或 PDF 识别为文档文本并入库，响应同样不回显识别全文：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/ocr \
  -F document_type=resume \
  -F lang=ch \
  -F file=@/path/to/resume.png
```

OCR 默认使用 CPU 版 PaddleOCR。可通过 `OCR_DEVICE`、`OCR_DEFAULT_LANG`、`OCR_MAX_UPLOAD_MB` 调整设备、默认语言和上传大小限制。

## 启用本地 Ollama 大模型抽取

安装 Ollama macOS app：

1. 从 `https://ollama.com/download/mac` 下载官方 macOS 安装包；
2. 将 `Ollama.app` 放入 `/Applications`；
3. 确认命令行可用：

```bash
ollama --version
```

如果桌面 app 没有自动启动本地服务，可以用命令行启动：

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

拉取推荐的千问 7B 模型：

```bash
ollama pull qwen2.5:7b
ollama list
```

启用后端本地 LLM adapter：

```bash
export LLM_BACKEND=ollama
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:7b
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_INPUT_CHARS=12000
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

验证 Ollama 服务与后端能力状态：

```bash
curl http://127.0.0.1:11434/api/tags
curl http://127.0.0.1:8000/api/v1/capabilities
```

常见排错：

- `curl: Failed to connect to 127.0.0.1 port 11434`：先启动 `ollama serve` 或打开 `Ollama.app`；
- `model not found`：执行 `ollama pull qwen2.5:7b`；
- 画像接口返回 `state=not_implemented` 且有 `warnings`：模型调用失败或模型没有输出严格 JSON，后端已自动降级为 mock，服务不会中断；
- 本地模型响应慢：减小 `LLM_MAX_INPUT_CHARS`，或换更小模型。

详细接口契约见 [docs/api-v3.md](docs/api-v3.md)。Neo4j 与知识图谱使用方法见 [docs/项目工作与Neo4j知识图谱使用说明.md](docs/项目工作与Neo4j知识图谱使用说明.md)。第一次接触项目或准备替换论文算法时，建议先读 [docs/零基础项目导读与算法替换指南.md](docs/零基础项目导读与算法替换指南.md)。
