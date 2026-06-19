# 比赛 Demo 讲解脚本

这份脚本用于现场向评委演示完整链路。建议先启动后端，再按顺序展示样例、解析、匹配、图谱、演化和 LLM 预留能力。

## 1. 启动后端

```bash
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://127.0.0.1:8000/
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

说明 `/health` 返回 `{"status":"ok"}`，表示 FastAPI demo 后端已正常启动。

## 2. 展示样例 JD 和简历

打开：

- `data/samples/jd_samples.json`
- `data/samples/resume_samples.json`

讲解点：

- JD 样例包含岗位标题、领域、级别、原始文本和预期匹配简历；
- 简历样例包含候选人、目标岗位、教育背景、工作年限、强技能和原始文本；
- 用户爬取的 100 条 JD/简历 raw 数据后续可接入同一套解析与评测流程。

## 3. 调用 JD 解析

```bash
curl -X POST http://127.0.0.1:8000/parse/jd \
  -H "Content-Type: application/json" \
  -d '{"text":"岗位名称: 大模型算法工程师\n任职要求: 熟练掌握 Python、PyTorch、RAG。","use_llm":false}'
```

讲解点：

- 默认使用规则算法，不调用真实大模型；
- 输出岗位结构化画像、技能、权重、能力域和证据；
- 产物写入 `data/raw/jd`、`data/parsed/jd_profiles`、`data/normalized` 和 `data/evidence`。

## 4. 调用简历解析

```bash
curl -X POST http://127.0.0.1:8000/parse/resume \
  -H "Content-Type: application/json" \
  -d '{"text":"姓名: 候选人A\n项目经历: 使用 Python、PyTorch、RAG 完成知识库问答系统。","use_llm":false}'
```

讲解点：

- 输出候选人画像、技能熟练度、近期经验和证据；
- 解析结果与 JD 画像共享统一技能归一化层，便于后续匹配和建图。

## 5. 调用人岗匹配

```bash
curl -X POST http://127.0.0.1:8000/match \
  -H "Content-Type: application/json" \
  -d '{"jd_text":"岗位名称: 大模型算法工程师\n任职要求: 熟练掌握 Python、PyTorch、RAG。","resume_text":"姓名: 候选人A\n项目经历: 使用 Python、PyTorch、RAG 完成知识库问答系统。","use_llm":false}'
```

重点展示：

- `final_score`：最终匹配分；
- `decision`：推荐决策；
- `matched_skills`：已满足技能；
- `missing_skills`：缺失技能；
- `partial_skills`：部分满足技能；
- `score_detail`：覆盖率、经验、教育、领域、语义等分项；
- `explanation`：规则解释和 LLM mock 说明。

## 6. 展示能力差距

在 `/match` 结果中展开：

```text
match_result.gap_analysis
```

讲解点：

- 缺失技能表示候选人简历没有证据支撑；
- 部分匹配技能表示存在相关经验，但熟练度或证据不足；
- 建议字段可用于生成学习路径、岗位培训建议或人才培养建议。

## 7. 展示 Match Graph

```bash
curl "http://127.0.0.1:8000/graph/view?view_type=match"
```

讲解点：

- `graph_match_view.json` 把候选人、岗位和技能点连接起来；
- 边关系区分 `matches`、`lacks`、`partially_matches`；
- 这比只返回一个匹配分更适合解释比赛中的“能力差距分析”。

## 8. 展示技术栈视图

```bash
curl "http://127.0.0.1:8000/graph/view?view_type=tech_stack"
```

讲解点：

- TechStack 节点将技能组织到 AI、后端、数据、云原生等技术栈；
- 评委可以看到岗位能力并非孤立技能词，而是有技术结构。

## 9. 展示能力等级视图

```bash
curl "http://127.0.0.1:8000/graph/view?view_type=level"
```

讲解点：

- Level 节点展示岗位要求等级和候选人熟练度；
- 同一个技能可以同时有“岗位要求强度”和“候选人掌握程度”。

## 10. 展示新岗位发现

```bash
curl -X POST http://127.0.0.1:8000/evolution/discover \
  -H "Content-Type: application/json" \
  -d '{"source_documents":[{"source_id":"jd1","text":"岗位名称: 大模型应用工程师\n要求: RAG、LangChain、知识库问答、模型部署。"},{"source_id":"jd2","text":"岗位名称: AI 应用工程师\n要求: 大语言模型、RAG、FastAPI、企业服务落地。"}],"use_llm":false}'
```

讲解点：

- 多条 JD 来源中反复出现的新技能组合会被聚合；
- 返回结果保留来源证据，便于解释“为什么认为这是新岗位方向”；
- 当前命名仍以规则为主，LLM 只预留命名增强入口。

## 11. 展示岗位动态更新

```bash
curl -X POST http://127.0.0.1:8000/evolution/update \
  -H "Content-Type: application/json" \
  -d '{"old_jd_text":"岗位名称: 后端工程师\n要求: Java、Spring Boot、MySQL。","new_jd_text":"岗位名称: 后端工程师\n要求: Java、Spring Boot、MySQL、Kafka、Kubernetes、微服务。","use_llm":false}'
```

讲解点：

- 返回新增、移除、变化技能；
- 可用于解释岗位能力随时间变化，例如后端岗位向云原生、消息队列、微服务演化；
- 演化结果可以进入 `graph_evolution_view.json`。

## 12. 说明 LLM 后续增强路径

展示目录：

```text
backend/app/llm
```

讲解点：

- 当前 demo 不接真实 LLM API；
- `use_llm=false` 是默认值；
- 即使传入 `use_llm=true`，没有配置真实 provider 时也只返回安全 mock 状态；
- 后续可在 JD 抽取、简历抽取、匹配解释、新岗位命名、岗位更新说明中接入 LLM；
- LLM 输出必须经过 JSON schema 校验、技能归一化和规则结果融合，不能直接覆盖算法主链路。
