# 系统架构

## 分层结构

```text
API 层 -> Service 层 -> Algorithm 层 -> Graph / Storage / LLM 层
```

- API 层：负责 HTTP 请求校验、响应模型和路由拆分，不承载核心算法。
- Service 层：编排 JD 解析、简历解析、人岗匹配、图谱读取、岗位演化分析和样例读取。
- Algorithm 层：保留现有规则算法，负责确定性的解析、技能归一化、匹配评分和能力差距分析。
- Graph 层：负责统一图谱 schema、完整图谱构建、视图图谱抽取和图谱文件读写。
- Storage 层：负责数据目录、稳定 ID、JSON 保存和样例/评测文件落盘。
- LLM 层：只作为安全 mock 和 prompt 预留层，默认不启用，不替代规则算法。

## 运行链路

1. `/parse/jd` 或 `/parse/resume` 接收文本。
2. Service 调用规则解析器、技能抽取器、归一化器和画像构建器。
3. Storage 分层保存 raw、parsed、normalized、evidence 等中间结果。
4. `/match` 同时解析 JD 和简历，调用匹配算法、差距分析、图谱构建和 LLM mock 解释。
5. Graph Repository 写出 `graph_full.json` 以及 5 个视图图谱。
6. API 返回 `final_score`、`decision`、命中/缺失/部分匹配技能、解释文本、兼容字段和 graph。

## 兼容策略

旧入口没有直接删除：

- `backend/main.py` 保留为兼容启动入口；
- `backend/app/api/router.py` 保留为聚合与兼容导出；
- 顶层 `algorithms/`、`input_adapters/` 保留兼容包装，核心逻辑迁移到 `backend/app/`。

推荐启动方式：

```bash
python3 -m uvicorn backend.app.main:app --reload
```
