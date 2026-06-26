# v3 Contract Skeleton

正式、版本化的岗位—能力图谱系统接口骨架。当前实现提供：

- 进程内资源管理；
- PaddleOCR 文档识别入口；
- 明确的 mock 智能能力边界；
- 可选 Neo4j 知识图谱写入与图谱路径检索。

默认配置仍使用 mock，不执行规则抽取、打分、LLM、RAG 或爬虫。设置 `GRAPH_BACKEND=neo4j` 后，`knowledge_graph` 与 `graph_rag` 会切换到 Neo4j adapter，用于后续部署岗位—技能—能力知识图谱。

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

详细接口契约见 [docs/api-v3.md](docs/api-v3.md)。Neo4j 与知识图谱使用方法见 [docs/项目工作与Neo4j知识图谱使用说明.md](docs/项目工作与Neo4j知识图谱使用说明.md)。第一次接触项目或准备替换论文算法时，建议先读 [docs/零基础项目导读与算法替换指南.md](docs/零基础项目导读与算法替换指南.md)。
