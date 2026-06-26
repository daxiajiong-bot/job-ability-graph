# v3 Contract Skeleton 架构

`API -> application use cases -> domain ports -> memory / mock / Neo4j adapters`。

路由只负责 HTTP 校验和错误映射；业务能力通过端口注入。当前默认注入的实现为：内存资源仓储、PaddleOCR，以及结构化抽取、技能归一化、画像、文档 RAG、知识图谱、GraphRAG、岗位演化、匹配和报告的 mock adapter。

设置 `GRAPH_BACKEND=neo4j` 后，`KnowledgeGraphPort` 与 `GraphRetrievalPort` 会替换为 Neo4j adapter。API 契约和路由保持不变：

- `POST /api/v1/knowledge-graphs`：从已有文档、候选人画像、岗位画像生成岗位—技能—能力—证据图谱，并写入 Neo4j；
- `POST /api/v1/graph-retrievals`：基于 Neo4j 中的图谱节点与关系返回路径证据；
- 其他尚未接入真实算法的能力继续返回显式 mock。

Neo4j adapter 位于 `backend/app/infrastructure/neo4j/`。它只负责图数据库读写，不在路由层或用例层嵌入算法。后续接入本地 7B、向量检索、技能归一化或图谱增强匹配时，仍按端口替换对应 adapter，不改变 API 契约。
