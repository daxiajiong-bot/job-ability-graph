# v3 Contract Skeleton 架构

`API -> application use cases -> domain ports -> memory/mock adapters`。

路由只负责 HTTP 校验和错误映射；业务能力通过端口注入。当前注入的实现为：内存资源仓储，以及结构化抽取、技能归一化、画像、文档 RAG、知识图谱、GraphRAG、岗位演化、匹配和报告的 mock adapter。

后续接入本地 7B、向量检索、Neo4j 或图谱增强匹配时，只替换对应 adapter，不改变 API 契约或路由。
