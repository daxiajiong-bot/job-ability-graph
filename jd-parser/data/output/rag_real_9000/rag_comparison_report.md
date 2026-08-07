# RAG 增强前后对比报告

## RAG 策略

本轮引入的是本地 RAG：

- 不调用外部 LLM API；
- 不使用外部向量数据库；
- 从已有 9000 条 Profile 构建技能检索索引；
- RAG 只召回候选技能；
- 候选技能必须再次在当前 JD 的 `raw_text` 中命中；
- 新增技能必须保存原文证据；
- 新增后仍通过 Validator 校验。

## Profile 增强结果

| 指标 | 数值 |
| --- | ---: |
| 原始 Profile 数 | 9000 |
| 增强后 Profile 数 | 9000 |
| 增强后 valid 数 | 9000 |
| 原始技能事实数 | 91576 |
| 增强后技能事实数 | 94382 |
| 新增技能事实数 | 2806 |
| 有新增技能的岗位数 | 2392 |
| 有新增技能的岗位比例 | 26.58% |

## 知识抽取指标对比

| 指标 | 原始抽取 | RAG 增强后 | 变化 |
| --- | ---: | ---: | ---: |
| skill_coverage | 0.9707 | 0.9778 | +0.0071 |
| required_skill_doc_coverage | 0.8831 | 0.8850 | +0.0019 |
| mentioned_skill_doc_coverage | 0.7834 | 0.8113 | +0.0279 |
| avg_skills_per_doc | 10.1751 | 10.4869 | +0.3118 |
| skill_evidence_support_rate | 1.0000 | 1.0000 | 0 |
| constraint_evidence_support_rate | 1.0000 | 1.0000 | 0 |
| lexicon_recall_proxy | 0.9673 | 1.0000 | +0.0327 |
| docs_with_candidate_but_no_skill_ratio | 0.0071 | 0.0000 | -0.0071 |
| docs_with_low_skill_density_ratio | 0.0651 | 0.0584 | -0.0067 |

## 图谱对比

| 指标 | 原始 KG | RAG KG | 变化 |
| --- | ---: | ---: | ---: |
| 节点数 | 84269 | 86285 | +2016 |
| 边数 | 232734 | 238346 | +5612 |
| 技能边数 | 91576 | 94382 | +2806 |
| jobs_with_skill_edges | 8736 | 8800 | +64 |
| jobs_without_skill_edges | 264 | 200 | -64 |
| evidence_text_missing_from_raw_text | 0 | 0 | 0 |
| dangling_edges | 0 | 0 | 0 |

## Top 新增技能

| 技能 | 新增次数 |
| --- | ---: |
| SQL | 383 |
| 模型微调 | 322 |
| 视觉算法 | 299 |
| 微调 | 208 |
| 算法开发 | 197 |
| Agent | 196 |
| 模型训练 | 177 |
| 机器视觉 | 129 |
| 人工智能 | 113 |
| 模型推理 | 102 |
| 模型部署 | 98 |
| 大模型 | 97 |
| 算法设计 | 82 |
| Go | 74 |
| Java | 64 |

## 结论

RAG 增强后，技能召回有所提升，同时证据支持率仍保持 100%。因此当前 RAG 引入是有效的，但它应继续作为“候选技能召回 + 证据门控”的辅助模块，而不是替代原有抽取器。

后续建议：

1. 加入人工金标集，计算技能抽取 precision / recall / F1；
2. 将 RAG 检索源从已有 Profile 扩展到人工维护技能词表、岗位族样例和标准职业能力词表；
3. 在写入 Profile 前继续强制执行 evidence 校验；
4. 在人岗匹配模型中优先使用 RAG 增强后的 `REQUIRES_SKILL / PREFERS_SKILL` 边。

