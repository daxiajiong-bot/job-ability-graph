# 知识图谱 RAG 数据文件治理

本文档说明项目内置的数据文件治理链路。目标是让简历、JD、政策、行业报告、市场数据等多源异构文件，从上传、登记、解析、清洗、切块、抽取、归一化、入图、RAG 检索到最终回答，都保留可审计的 `doc_id`、`chunk_id`、`version` 和 `evidence`。

## 目录契约

项目使用 `data/` 下的六个治理目录：

- `data/raw/`：原始文件的不可变版本副本。登记后按 `doc_id/v{version}/filename` 保存，后续流水线只读不改。
- `data/staging/`：解析、质量检测、清洗 chunk、候选实体、候选关系等中间产物。
- `data/structured/`：归一化后的结构化实体、关系和画像产物；LLM 画像落盘在 `data/structured/profiles/`。
- `data/graph/`：可写入图数据库的节点和边 JSON；每条边都绑定 evidence。
- `data/rag/`：RAG chunk 索引，检索结果直接引用这里的 `doc_id`、`chunk_id` 和 quote。
- `data/audit/`：文件登记表、hash 索引、版本索引和事件日志。
- `data/esco/`：官方 ESCO 快照索引缓存，默认版本为 `v1.2.1`。

可通过环境变量 `DATA_GOVERNANCE_ROOT` 改变治理产物根目录。ESCO 索引默认读取 `data/esco/index/concepts.jsonl`，可通过 `ESCO_INDEX_ROOT` 和 `ESCO_VERSION` 指定官方快照位置与版本。系统不维护运行时手写技能词表；旧手写样例只作为 legacy 数据保留，不参与抽取、归一化或画像处理。

## 核心 Schema

代码位置：`backend/app/data_governance/schemas.py`。

- `DocumentMetadata`：登记元数据，包含 `doc_id`、`version`、`content_hash`、`raw_path`、来源、原文件名和去重状态。
- `ParsedDocument`：解析后的文本视图，保留 `doc_id`、`version`、`raw_path`、`content_hash`。
- `Chunk`：切块结果，包含 `chunk_id`、字符区间、原始文件路径和 hash。
- `EntityCandidate`：实体候选，当前使用 Ollama draft、语言证书规则和 ESCO linking 做能力 span 抽取与概念对齐；候选包含 `surface`、`start_char`、`end_char`、`normalized_name`、`lskt_label`、`normalization_status`、`esco_uri`、`esco_preferred_label`、`esco_version`、`linking_status`、`linking_confidence` 和 evidence。
- `RelationCandidate`：关系候选，必须经过归一化和 evidence 绑定后才能进入图谱构建。
- `GraphNode` / `GraphEdge`：图谱节点和边。语义边如 `HAS_SKILL`、`REQUIRES_SKILL`、`MENTIONS_SKILL` 都带 evidence。
- `Evidence`：原文证据，包含 `doc_id`、`chunk_id`、`quote`、字符区间、`raw_path` 和 `content_hash`。

## 流程

1. 文件登记

   上传或本地路径登记都会计算 SHA-256。相同 hash 直接返回 `status=duplicate`，不会重复复制 raw 文件；相同 `source_system + external_id` 但内容变化，会复用 `doc_id` 并创建新版本。

2. 原文保存

   新文件会复制到 `data/raw/{doc_id}/v{version}/`。后续所有步骤只读取 raw 副本，不修改 raw。

3. 解析和质量检测

   当前内置文本、CSV、JSON、JSONL 解析器。质量报告写入 `data/staging/{doc_id}/v{version}/quality.json`，至少检查原文、清洗文本、`doc_id`、版本号。

4. 清洗和切块

   清洗只做换行、空白和控制字符规范化。chunk 写入 staging 与 rag，每个 chunk 都带 `doc_id`、`version`、`chunk_id`、`raw_path` 和 `content_hash`。

5. 候选抽取和 ESCO linking

   能力候选先由本地 Ollama 生成 LSKT span draft，语言证书类 span 保留少量本地规则兜底；随后 `EscoLinker` 使用官方 ESCO 快照索引召回候选，并让 Ollama 只能从候选 `esco_uri` 中选择。LSKT 只作为能力分类字段：`K`=知识/理论/标准，`S`=可执行技能，`T`=通用能力，`L`=语言能力。抽取结果先成为 `EntityCandidate` 和 `RelationCandidate`，关系候选的 `validation_status` 必须表明已通过 span、ESCO linking 和 evidence 绑定。

   证据闸门是强约束：`surface` 必须能从清洗文本中按 `start_char/end_char` 切回，`Evidence.quote` 必须包含该 `surface`。无法定位、边界不合法、标签不属于 K/S/T/L 或证据不包含 span 的候选不会写入 structured、graph 或 rag。

   可通过 `LSKT_SPAN_BACKEND` 控制抽取来源：

   - `ollama`：默认值，调用 Ollama 生成能力 span draft，再执行同样的证据闸门；
   - `hybrid`：当前等价于 `ollama` 加语言证书规则，保留给后续扩展；
   - `local`：只保留语言证书规则，不做技能词典匹配，适合断网排查证据链。

   Ollama 连接参数复用 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_TIMEOUT_SECONDS` 和 `LLM_MAX_INPUT_CHARS`。链接阈值可通过 `ESCO_LINK_MIN_CONFIDENCE` 调整。模型返回的 URI 不在候选列表、置信度低于阈值或没有候选时，结果保留 `surface` 并标记为 `linking_status="unmapped"`；系统不会生成原文不存在的技能，也不会硬贴 ESCO。

   ESCO 索引字段固定为 `esco_uri`、`concept_type`、`preferred_label`、`alt_labels`、`description`、`scope_note`、`skill_type`、`reuse_level`、`broader_uris`、`lskt_label`、`version`。没有 ESCO 索引时服务会明确报错，避免演示时静默降级。

6. 图谱构建

   图谱产物写入 `data/graph/{doc_id}/v{version}/graph.json`。图中包含 Document、Chunk、Skill、Evidence 节点，以及 `CONTAINS_CHUNK`、`HAS_SKILL`、`REQUIRES_SKILL`、`MENTIONS_SKILL` 等边。链接成功的 Skill 节点 ID 使用 `esco_uri`；未映射的新兴能力使用稳定哈希 ID，并保留 `linking_status="unmapped"` 或后续可扩展的 `emerging_candidate`。LSKT 不单独建成完整图谱 schema，只作为 Skill 节点和语义边的属性。每条边都包含 `evidence_ids` 和 evidence 明细。

7. RAG 检索和回答

   `/api/v1/data-governance/rag/search` 返回命中的 chunk 和 quote；`/api/v1/data-governance/rag/answer` 只基于检索到的 quote 组织回答。RAG chunk 同时携带 `skills`、`competency_spans`、`lskt_labels` 和 `evidence_ids`。没有命中 evidence 时，不生成无来源结论。

说明：严格执行文件登记、候选校验、归一化和 evidence 绑定的链路是 `/api/v1/data-governance`。原有 `/api/v1/knowledge-graphs` 仍保留 v3 合同中的 profile 图谱能力，用于兼容已有画像/Neo4j 流程。

设置 `LLM_BACKEND=ollama` 后，`/api/v1/candidate-profiles` 和 `/api/v1/job-profiles` 会生成 `profile-extraction/v2` 的 `ResumeProfile` / `JDProfile`，并把解析产物写入 `data/structured/profiles/{candidate|job}/`。返回体中的 `profile.artifacts.profile_json` 指向具体 JSON 文件。

## API

上传登记：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/documents/register \
  -F document_type=jd \
  -F source_system=manual \
  -F external_id=jd-001 \
  -F file=@/path/to/jd.txt
```

本地路径登记：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/documents/register-path \
  -H 'Content-Type: application/json' \
  -d '{"document_type":"resume","path":"/absolute/path/resume.txt","source_system":"local","external_id":"resume-001"}'
```

处理文档：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/documents/{doc_id}/process \
  -H 'Content-Type: application/json' \
  -d '{}'
```

查看追溯链：

```bash
curl http://127.0.0.1:8000/api/v1/data-governance/documents/{doc_id}/lineage
```

检索和回答：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/data-governance/rag/answer \
  -H 'Content-Type: application/json' \
  -d '{"query":"Python MySQL 要求","doc_ids":["doc_xxx"],"top_k":5}'
```

## 约束

- raw 原始副本不可修改，流水线只读。
- 所有中间产物必须带 `doc_id` 和 `version`。
- 所有 chunk 必须能追溯到 `raw_path` 和 `content_hash`。
- LLM 抽取结果不能直接入图；必须先转成候选、校验、归一化并绑定 evidence。
- 运行时能力标准来源是官方 ESCO 快照索引，代码不维护手写技能 canonical/alias 词表。
- 不伪造 evidence；RAG 回答只引用真实 chunk quote。
- 治理能力直接通过 `/api/v1/data-governance` 接入项目。

## ESCO 索引导入

默认使用官方 ESCO `v1.2.1` CSV 快照。官方下载页面可能需要人工选择包或邮箱确认，因此代码只接收本地已下载的 zip 或 CSV 目录，不在运行时访问在线 API。

```bash
python3 scripts/build_esco_index.py \
  --source /path/to/esco-csv-or-zip \
  --output-root data/esco \
  --version v1.2.1
```

导入脚本会读取 `skills` 和 `broaderRelationsSkillPillar` 等 CSV，生成 `data/esco/index/concepts.jsonl` 和 `manifest.json`。仓库内的 `data/esco` 是最小测试索引，只用于保证本地测试和接口 smoke 可运行；比赛演示应替换为官方完整快照。

## 验证

基础单元测试不依赖外部模型：

```bash
python3 -m unittest tests.unit.test_data_governance tests.unit.test_llm_adapters tests.unit.test_mock_adapters
```

真实 Ollama smoke 可在本机服务启动后执行：

```bash
curl http://127.0.0.1:11434/api/tags
export LSKT_SPAN_BACKEND=ollama
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:7b
export ESCO_INDEX_ROOT=data/esco
export ESCO_VERSION=v1.2.1
python3 -m unittest tests.unit.test_data_governance
```
