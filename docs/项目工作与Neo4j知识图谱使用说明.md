# 项目工作与 Neo4j 知识图谱使用说明

## 1. 本次新增项目工作

本次更新把“岗位—技能—能力知识图谱层”从预留接口推进到可部署的最小闭环：

| 工作 | 位置 | 作用 |
| --- | --- | --- |
| Neo4j 图谱构建 adapter | `backend/app/infrastructure/neo4j/adapters.py` | 实现 `KnowledgeGraphPort`，把文档、候选人画像、岗位画像、技能、能力、证据写入 Neo4j |
| Neo4j 图谱检索 adapter | `backend/app/infrastructure/neo4j/adapters.py` | 实现 `GraphRetrievalPort`，返回实体与路径证据，供后续 GraphRAG 使用 |
| 后端装配开关 | `backend/app/infrastructure/wiring.py` | 通过 `GRAPH_BACKEND=mock/neo4j` 切换 mock 或真实 Neo4j |
| Neo4j 运行配置 | `.env.example`、`docker-compose.neo4j.yml`、`scripts/neo4j.sh` | 提供本地部署数据库的默认参数和常用 Docker 命令 |
| 使用文档 | `README.md`、本文件、`docs/architecture-v3.md`、`docs/api-v3.md` | 说明项目工作、启动方式、图谱模型和使用流程 |

这一步对应比赛技术路线中的第 6 层“岗位—技能—能力知识图谱层”，也为后续图谱增强人岗匹配、动态演化分析和混合 GraphRAG 证据解释打基础。

## 2. Neo4j 在本项目里的角色

本项目不是把 Neo4j 当成普通表格数据库，而是用它保存可以被解释和推理的关系：

- 候选人画像拥有哪些技能；
- 岗位画像要求哪些技能；
- 技能属于哪个能力域；
- 画像依据哪些原文证据；
- 一次图谱构建使用了哪些文档和画像。

这样做的价值是：后续生成匹配报告或趋势报告时，系统不仅能说“匹配/不匹配”，还能给出图谱路径，例如：

```text
候选人画像 -> HAS_SKILL -> Python
岗位画像 -> REQUIRES_SKILL -> Python
Python -> BELONGS_TO_CAPABILITY -> 数据分析能力
```

这些路径可以和文档证据一起进入 GraphRAG，增强答辩中“为什么这样判断”的可解释性。

## 3. 当前图谱模型

### 节点

| 节点标签 | 含义 |
| --- | --- |
| `JobAbilityGraphSnapshot` | 一次图谱构建快照 |
| `SourceDocument` | 简历、JD、政策、行业报告、市场数据等来源文档 |
| `CandidateProfile` | 候选人画像 |
| `JobProfile` | 岗位画像 |
| `Skill` | 技能节点 |
| `Capability` | 能力域节点 |
| `Evidence` | 证据片段或证据引用 |

### 关系

| 关系类型 | 含义 |
| --- | --- |
| `USES_DOCUMENT` | 图谱快照使用了某个文档 |
| `USES_PROFILE` | 图谱快照使用了某个画像 |
| `DERIVED_FROM` | 画像来自某个文档 |
| `HAS_SKILL` | 候选人拥有某项技能 |
| `REQUIRES_SKILL` | 岗位要求某项技能 |
| `HAS_CAPABILITY` | 候选人具备某类能力 |
| `REQUIRES_CAPABILITY` | 岗位要求某类能力 |
| `BELONGS_TO_CAPABILITY` | 技能归属某个能力域 |
| `SUPPORTED_BY` | 画像由证据支持 |

当前 mock 画像中的技能和能力为空，所以只会写入文档、画像和快照关系。后续接入结构化抽取、技能归一化、画像构建后，`attributes.skills`、`attributes.capabilities` 和 `evidence` 会自动映射成图谱节点和关系。

## 4. 启动 Neo4j

在项目根目录先复制环境变量模板：

```bash
cp .env.example .env
```

`.env` 可以调整这些关键配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NEO4J_PASSWORD` | `jobgraph_neo4j_2026` | 本地 Neo4j 管理员密码 |
| `NEO4J_HTTP_PORT` | `7474` | Neo4j Browser 端口 |
| `NEO4J_BOLT_PORT` | `7687` | 后端连接 Neo4j 的 Bolt 端口 |
| `NEO4J_HEAP_INITIAL` | `768M` | JVM 初始堆内存 |
| `NEO4J_HEAP_MAX` | `1536M` | JVM 最大堆内存 |
| `NEO4J_PAGECACHE` | `1G` | 图数据页缓存 |

本地比赛演示推荐保留默认内存配置：总占用约 2.5GB 以内，足够当前岗位—技能—能力图谱 demo 使用；如果机器内存紧张，可把 `NEO4J_HEAP_MAX` 改成 `1g`、`NEO4J_PAGECACHE` 改成 `512m`。

推荐使用脚本启动：

```bash
scripts/neo4j.sh start
```

等价的原始 Docker Compose 命令是：

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

浏览器打开：

```text
http://localhost:7474
```

默认账号：

```text
username: neo4j
password: jobgraph_neo4j_2026
```

如果你不用 Docker，也可以安装本地 Neo4j，只要保证 Bolt 地址、用户名、密码与环境变量一致。

常用 Docker 管理命令：

```bash
scripts/neo4j.sh status    # 查看容器状态
scripts/neo4j.sh logs      # 跟随日志
scripts/neo4j.sh shell     # 进入 cypher-shell
scripts/neo4j.sh browser   # 打印 Browser/Bolt 地址
scripts/neo4j.sh stop      # 停止容器，保留数据卷
scripts/neo4j.sh reset     # 删除容器和本地 Neo4j 数据卷
```

如果不使用脚本，对应命令为：

```bash
docker compose -f docker-compose.neo4j.yml ps
docker compose -f docker-compose.neo4j.yml logs -f neo4j
docker exec -it job-ability-neo4j cypher-shell -u neo4j -p jobgraph_neo4j_2026
docker compose -f docker-compose.neo4j.yml down
docker compose -f docker-compose.neo4j.yml down -v
```

## 5. 启动后端并启用 Neo4j

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

建议使用 Python 3.10+。Neo4j 当前 Python driver 6.x 要求 Python 3.10 或更高版本，项目源码本身也使用了现代类型标注语法。

启用 Neo4j adapter：

```bash
export GRAPH_BACKEND=neo4j
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=jobgraph_neo4j_2026
export NEO4J_DATABASE=neo4j
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

检查能力是否切换成功：

```bash
curl http://127.0.0.1:8000/api/v1/capabilities
```

返回中应看到：

```json
{"name": "knowledge_graph", "implementation": "neo4j", "state": "available"}
```

## 6. API 使用流程

### 6.1 创建简历文档

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "document_type": "resume",
    "text": "匿名候选人：熟悉 Python、机器学习和知识图谱项目。",
    "source": {"source_system": "manual", "external_id": "resume-demo-001"}
  }'
```

记录返回的 `data.document.id`。

### 6.2 创建 JD 文档

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "document_type": "jd",
    "text": "岗位要求：掌握 Python、知识图谱、RAG 和数据分析。",
    "source": {"source_system": "manual", "external_id": "jd-demo-001"}
  }'
```

记录返回的 `data.document.id`。

### 6.3 创建候选人画像与岗位画像

```bash
curl -X POST http://127.0.0.1:8000/api/v1/candidate-profiles \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"上一步简历doc_id"}'

curl -X POST http://127.0.0.1:8000/api/v1/job-profiles \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"上一步JD doc_id"}'
```

当前画像仍是 mock，所以 `attributes.skills` 为空。真实抽取 adapter 接入后，这一步会产出可写入图谱的技能、能力和证据。

### 6.4 创建知识图谱

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-graphs \
  -H 'Content-Type: application/json' \
  -d '{
    "candidate_profile_ids": ["候选人profile_id"],
    "job_profile_ids": ["岗位profile_id"]
  }'
```

返回的 `data.knowledge_graph` 中会包含图谱快照节点、画像节点、文档节点和关系。Neo4j 中也会同步写入这些节点关系。

### 6.5 图谱检索

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/graph-retrievals?graph_id=graph_id' \
  -H 'Content-Type: application/json' \
  -d '{"query":"Python","seed_entity_ids":[],"relation_types":[]}'
```

返回的 `paths` 可以作为后续报告生成或 GraphRAG 的图谱证据。

## 7. Neo4j Browser 查询示例

查看所有节点：

```cypher
MATCH (n)
RETURN n
LIMIT 100;
```

查看图谱快照使用了哪些资源：

```cypher
MATCH (g:JobAbilityGraphSnapshot)-[r]->(n)
RETURN g, r, n
LIMIT 100;
```

查看候选人与岗位的技能关系：

```cypher
MATCH path=(p)-[r:HAS_SKILL|REQUIRES_SKILL]->(s:Skill)
RETURN path
LIMIT 100;
```

查看技能到能力域的归属：

```cypher
MATCH path=(s:Skill)-[:BELONGS_TO_CAPABILITY]->(c:Capability)
RETURN path
LIMIT 100;
```

清空本地演示图谱：

```cypher
MATCH (n)
DETACH DELETE n;
```

## 8. 后续怎么继续增强

推荐顺序：

1. 接入结构化抽取 adapter，让简历和 JD 输出 `skills`、`capabilities`、`evidence`。
2. 接入技能归一化，把“RAG”“Retrieval-Augmented Generation”“检索增强生成”等映射到同一技能节点。
3. 扩展图谱属性，加入时间、行业、地区、岗位层级和技能热度。
4. 在匹配 adapter 中读取 Neo4j 路径，把技能重合、能力缺口、学习路径变成可解释分数。
5. 在报告生成 adapter 中结合文档证据和图谱路径，生成面向评委的可追溯解释。

比赛展示时，不建议只展示大而空的图。更有说服力的是展示一条可追溯链路：原始 JD/简历片段 -> 结构化技能 -> Neo4j 路径 -> 匹配差距或趋势结论。
