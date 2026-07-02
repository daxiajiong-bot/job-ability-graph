# 项目日志

## 2026-06-29 ESCO 快照索引替换手写词表

- 新增 `backend/app/data_governance/esco.py` 和 `scripts/build_esco_index.py`，支持从官方 ESCO CSV/zip 快照生成本地只读索引，默认版本为 `v1.2.1`。
- 数据治理链路改为“原文 LSKT span 抽取 + ESCO 候选召回 + Ollama 候选内选择 + evidence 闸门”，不再依赖运行时手写 canonical/alias 技能词表。
- `EntityCandidate`、图谱 Skill 节点、语义边和 RAG chunk 均写入 `esco_uri`、`esco_preferred_label`、`esco_version`、`linking_status`、`linking_confidence`；未链接结果保留中文 `surface` 并标记 `unmapped`。
- `Skill` 节点链接成功时使用 `esco_uri` 作为标准 ID，未映射能力使用稳定哈希 ID，为后续新兴能力发现和图谱演化分析留入口。
- 保留少量语言证书本地规则用于证据抽取兜底；普通技能不再做本地词典匹配。缺少 ESCO 索引时服务明确报错，避免比赛演示静默降级。
- 更新 README 和数据治理文档，明确系统采用官方 ESCO 快照索引，不维护手写技能词表。

## 2026-06-29 Chinese-SkillSpan 简化 LSKT span 抽取

- 在 `backend/app/data_governance/` 中新增 LSKT 能力 span 抽取能力，将 Chinese-SkillSpan 的 K/S/T/L 分类简化接入现有治理链路。
- LSKT 仅作为能力分类字段，不替代完整知识图谱 schema；图谱仍保留 Document、Chunk、Skill、Evidence 和语义边。
- 扩展 `EntityCandidate`、图谱节点/边和 RAG chunk 产物，写入 `surface`、`start_char`、`end_char`、`lskt_label`、`normalization_status`、ESCO 字段和 evidence。
- 抽取默认使用本地 Ollama 生成 draft 候选；所有候选都必须通过原文 span 和 evidence quote 校验。
- 早期试验中的手写技能样例已移出运行链路，当前标准能力来源为 ESCO 快照索引。
- 新增测试覆盖 K/S/T/L 分类、span offset、evidence 包含约束、图谱/RAG 产物字段，以及 Ollama draft 中不存在于原文的候选丢弃规则。

## 2026-06-28 数据文件治理接入

- 新增 `backend/app/data_governance/` 模块，覆盖文件登记、hash 去重、版本管理、质量检测、解析、清洗、chunk 切分、技能候选抽取、技能归一化、关系候选、图谱节点/边构建和最小 RAG。
- 新增 `/api/v1/data-governance` 路由，治理能力直接接入现有 FastAPI 项目。
- 新增 `data/raw`、`data/staging`、`data/structured`、`data/graph`、`data/rag`、`data/audit` 目录契约。
- 初始版本曾使用外部数据文件承载技能归一化样例；当前已演进为官方 ESCO 快照索引。
- 图谱边和 RAG citations 均携带 evidence；回答接口返回 `doc_id`、`chunk_id` 和 quote。
- 新增 `tests/unit/test_data_governance.py`，覆盖登记、去重、版本、处理、图谱 evidence 和 RAG citation。
