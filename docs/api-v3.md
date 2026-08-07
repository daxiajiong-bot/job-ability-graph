# v3 API Contract

所有 `/api/v1` 成功响应使用 `data` 与 `meta` 信封；`meta` 包含 `request_id`、`api_version`、`implementation`、`persistence`。错误响应使用 `error.code`、`error.message`、`error.details`。

资源接口包括 documents、candidate-profiles、job-profiles、knowledge-graphs、matches 和 reports；能力接口包括 document-retrievals、graph-retrievals、position-discoveries 和 position-deltas。

数据治理接口位于 `/api/v1/data-governance`：

- `POST /documents/register`：上传文件，登记为带 `doc_id` 和 `version` 的 raw 副本；
- `POST /documents/register-path`：登记本地路径文件，会复制到 `data/raw`，不修改原路径文件；
- `POST /documents/{doc_id}/process`：执行解析、质量检测、清洗、切块、候选抽取、归一化、入图产物生成和 RAG chunk 索引；
- `GET /documents/{doc_id}/lineage`：查看 raw、staging、structured、graph、rag、audit 的追溯链；
- `POST /rag/search`：返回命中的 `doc_id`、`chunk_id`、quote；
- `POST /rag/answer`：只基于命中 quote 生成带 citations 的回答。

`POST /api/v1/documents/ocr` 接收 `multipart/form-data`，必填字段为 `document_type` 与 `file`，可选字段包括 `lang`、`source_system`、`external_id`、`uri`、`published_at`、`metadata_json` 以及 PaddleOCR 参数 `use_doc_orientation_classify`、`use_doc_unwarping`、`use_textline_orientation`、`text_det_limit_side_len`、`text_det_limit_type`、`text_det_thresh`、`text_det_box_thresh`、`text_det_unclip_ratio`、`text_rec_score_thresh`。接口支持常见图片与 PDF，识别出的全文只写入文档资源，不在响应中回显。

OCR 能力使用 `implementation: "paddleocr"`。默认配置下，除 OCR 和文档仓储外，智能接口仍返回 `state: "not_implemented"`，空数组或 `score: null`。这些值不是算法结论，客户端必须依据 `state` 与 `implementation` 决定是否展示。

当服务以 `GRAPH_BACKEND=neo4j` 启动时：

- `GET /api/v1/capabilities` 中的 `knowledge_graph` 与 `graph_rag` 会显示 `implementation: "neo4j"`、`state: "available"`；
- `POST /api/v1/knowledge-graphs` 会返回 `implementation: "neo4j"`，并将图谱节点关系写入 Neo4j；
- `POST /api/v1/graph-retrievals?graph_id=...` 会从 Neo4j 返回 `entities` 与 `paths`，用于后续 GraphRAG、匹配解释和趋势报告。

Neo4j adapter 当前不直接保存完整原文，只保存文档摘要属性、画像属性 JSON、技能/能力节点和证据片段引用。完整文档原文仍在进程内资源中，服务重启后会清空。

当 `LLM_BACKEND=ollama` 时，`POST /api/v1/candidate-profiles` 和 `POST /api/v1/job-profiles` 返回的 profile 会包含 `attributes.resume_profile` 或 `attributes.jd_profile`，并在 `artifacts.profile_json` 中给出落盘 JSON 路径。默认路径为 `data/structured/profiles/`，可通过 `PROFILE_ARTIFACT_ROOT` 调整。
