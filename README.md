# v3 Contract Skeleton

正式、版本化的岗位—能力图谱系统接口骨架。当前实现只提供进程内资源管理和明确的 mock 能力；不执行规则抽取、打分、LLM、RAG、Neo4j 或爬虫。

## 启动

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

- 健康检查：`GET /health`
- OpenAPI：`/docs`
- 正式 API：`/api/v1`

## 快速示例

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{"document_type":"resume","text":"匿名简历原文","source":{"source_system":"manual"}}'
```

响应仅返回文档元数据、长度和摘要校验值，不回显原文。服务重启后，所有资源都会清空。

详细接口契约见 [docs/api-v3.md](docs/api-v3.md)。第一次接触项目或准备替换论文算法时，建议先读[零基础项目导读与算法替换指南](docs/零基础项目导读与算法替换指南.md)。
