# JD 知识抽取效果评估报告

- Profile 数量：10000
- RAG 建议：`optional`

## 核心指标

| 指标 | 数值 | 含义 |
| --- | ---: | --- |
| title_coverage | 1.0 | 有岗位名称的比例 |
| skill_coverage | 0.9781 | 至少抽到一个技能的岗位比例 |
| required_skill_doc_coverage | 0.8849 | 有必需技能的岗位比例 |
| preferred_skill_doc_coverage | 0.4832 | 有优先技能的岗位比例 |
| education_coverage | 0.9874 | 有学历要求的岗位比例 |
| experience_coverage | 0.7702 | 有经验年限要求的岗位比例 |
| location_coverage | 0.9007 | 有地点信息的岗位比例 |
| avg_skills_per_doc | 10.4912 | 平均每条岗位抽取技能数 |
| skill_evidence_support_rate | 1.0 | 技能证据可回溯到原文的比例 |
| constraint_evidence_support_rate | 1.0 | 约束证据可回溯到原文的比例 |
| lexicon_recall_proxy | 1.0 | 基于当前技能词表复扫 raw_text 的召回代理指标 |
| docs_with_candidate_but_no_skill_ratio | 0.0 | 原文含候选技能词但 Profile 无技能的岗位比例 |
| docs_with_low_skill_density_ratio | 0.0578 | 技能数小于等于 1 的岗位比例 |

## RAG 是否需要加入

- 技能表面词数量较少，RAG 更适合用于术语扩展和技能归一化。

### 建议策略
- 优先保留当前证据优先抽取流程，RAG 只作为候选术语/相似 JD 样例检索器。
- RAG 返回的术语必须再次在 raw_text 中命中，不能直接写入 Profile。
- 用于提升召回时，建议检索技能词表、岗位族样例、人工标注样例，而不是检索泛化解释文本。
- 用于人岗匹配前，建议把 RAG 放在技能归一化与岗位族对齐阶段，而不是替代 evidence 校验。

## 高频已抽取技能

| 技能 | 次数 |
| --- | ---: |
| 大模型 | 9068 |
| Python | 6178 |
| 深度学习 | 5276 |
| 人工智能 | 4746 |
| Agent | 4561 |
| C++ | 3960 |
| RAG | 3421 |
| 机器学习 | 3398 |
| PyTorch | 2495 |
| 微调 | 2382 |
| 图像处理 | 2151 |
| TensorFlow | 2102 |
| 多模态 | 2047 |
| 算法开发 | 1995 |
| 架构设计 | 1921 |
| 模型训练 | 1850 |
| Java | 1834 |
| 机器视觉 | 1664 |
| 计算机视觉 | 1552 |
| Linux | 1487 |

## 可能漏抽的候选术语

| 候选术语 | 次数 |
| --- | ---: |
| .NET | 1 |
| Spring Boot | 1 |

说明：该报告是无人工标注情况下的自动代理评估。若要证明 JD 解析准确率 ≥90%，仍需要构造人工金标集计算 precision / recall / F1。
