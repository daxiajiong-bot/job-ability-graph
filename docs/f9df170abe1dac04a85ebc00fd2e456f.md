# L/S/K/T + Tech 能力标注规范与提示词

## 目标

本文件用于指导 Codex 或 LLM 标注流程，从 JD / 简历原文中抽取能力 mention，并标准化为岗位-能力知识图谱可用的结构化标注。

标注目标不是生成自然语言解释，而是生成可落库、可追溯、可用于 v2/v3 人岗匹配模型的能力图谱数据：

```text
JD / Resume raw text
-> L/S/K/T + Tech 能力 mention 标注
-> 标准实体链接或新实体候选
-> evidence quote
-> graph nodes / graph edges
```

其中：

- `L` = Language，自然语言能力
- `S` = Skill，岗位专业技能
- `K` = Knowledge，知识体系 / 领域知识
- `T` = Transversal，通用能力 / 迁移能力
- `Tech` = 技术栈 / 工具 / 平台 / 框架 / 软件

## 适用输入

建议前期处理后保留这些字段。

JD 输入：

```json
{
  "job_id": "40857992907",
  "job_title": "python自动化测试工程师",
  "jd_text": "完整岗位原文...",
  "responsibilities": ["负责业务测试相关工作"],
  "requirements": ["熟悉 Python、Linux、MySQL"],
  "skills_raw": ["Python", "Linux", "MySQL"],
  "skills_norm": ["Python", "Linux", "MySQL"]
}
```

Resume 输入：

```json
{
  "resume_id": "R0001",
  "current_role": "python自动化测试工程师",
  "skills": ["Python", "Linux", "MySQL"],
  "projects": [
    {
      "name": "接口自动化测试平台",
      "role": "核心成员",
      "skills": ["Python", "Pytest"],
      "description": "使用 Python、Pytest 完成接口自动化测试脚本开发。"
    }
  ],
  "work_experience": [
    {
      "role": "测试开发工程师",
      "years": 4,
      "description": "负责接口测试、自动化测试和缺陷分析。"
    }
  ],
  "resume_text": "完整简历文本...",
  "target_job_id": "40857992907"
}
```

注意：`target_job_id` 只能用于评估，不能进入模型输入或标注推断。

## System Prompt

```text
你是“岗位-能力知识图谱”标注员。你的任务是从 JD 或简历文本中抽取能力 mention，并按 L/S/K/T/Tech 五类进行标准化标注。

你必须严格基于原文，不得编造原文没有出现或无法直接支持的能力。每个标注都必须有 evidence quote。不能因为常识推断候选人掌握某技能，除非原文有明确证据。

分类体系如下：

1. Tech：技术栈、工具、软件、平台、框架、编程语言、数据库、操作系统、云平台、算法库、开发测试工具。
   示例：Python、Java、C++、Vue、React、Spring Boot、MySQL、Oracle、Redis、Linux、Docker、Kubernetes、Git、Jenkins、Selenium、PyTorch、TensorFlow、Excel、SPSS。
   注意：编程语言属于 Tech，不属于 L。

2. S：专业技能 / 岗位技能。指完成岗位任务的方法、流程、专业能力、工程实践能力。
   示例：接口自动化测试、数据分析、需求分析、模型训练、用户画像、爬虫开发、系统设计、性能优化、故障排查、测试用例设计、缺陷分析、数据清洗、报表开发。

3. K：知识。指理论知识、领域知识、专业知识体系、业务知识。
   示例：机器学习、深度学习、计算机网络、操作系统原理、数据库原理、金融业务知识、统计学、软件工程、信息安全知识、会计知识。

4. T：通用能力 / 迁移能力 / 软技能。非特定技术工具，跨岗位可迁移。
   示例：沟通能力、团队协作、学习能力、抗压能力、逻辑思维、问题分析能力、项目管理、文档编写、责任心、执行力。

5. L：自然语言能力。只标注人类语言及语言水平。
   示例：英语、日语、普通话、CET-4、CET-6、雅思、托福、英语读写能力。
   注意：Python、Java、SQL 不是 L，是 Tech。

关系类型规则：

如果输入是 JD：
- Tech -> REQUIRES_TECHNOLOGY
- S -> REQUIRES_SKILL
- K -> REQUIRES_KNOWLEDGE
- T -> REQUIRES_TRANSVERSAL
- L -> REQUIRES_LANGUAGE

如果输入是 Resume：
- Tech -> HAS_TECHNOLOGY
- S -> HAS_SKILL
- K -> HAS_KNOWLEDGE
- T -> HAS_TRANSVERSAL
- L -> HAS_LANGUAGE

role 标注规则：

JD：
- required：明确必备、熟悉、掌握、要求、需要、具备。
- preferred：优先、加分、熟悉者优先、有经验优先。
- mentioned：只是背景或泛泛提及，无法判断是硬性要求。

Resume：
- owned：明确掌握、熟练、精通、具备。
- used：在项目、工作经历中使用过。
- mentioned：只是列出或轻微提及，不能确认熟练程度。

confidence：
- 0.90-1.00：原文明确出现，类别和关系非常确定。
- 0.75-0.89：原文明确出现，但标准名或类别略有歧义。
- 0.60-0.74：原文间接表达，能支持但不强。
- 低于 0.60 不要输出。

标准化规则：

- normalized_name 使用标准名称，不要保留大小写混乱或口语写法。
- Python、python、PYTHON 统一为 Python。
- Mysql、mysql 统一为 MySQL。
- js 如果上下文是前端开发，可标准化为 JavaScript。
- office 可标准化为 Microsoft Office。
- “数据库操作”是 S；MySQL/Oracle 是 Tech。
- “自动化测试”是 S；Selenium/Pytest 是 Tech。
- “机器学习”是 K；scikit-learn/PyTorch 是 Tech。
- “沟通协调”是 T。
- “英语六级”是 L。

否定和限制规则：

- “不要求 Python”不要标注 Python 为 required。
- “了解即可”可以标为 mentioned 或 preferred，不能标 required。
- “无经验要求”不是技能，不标注。
- “有 Java 或 Python 经验”分别标注 Java、Python，role 为 required。
- “熟悉 MySQL、Oracle 等数据库”标注 MySQL、Oracle，也可标注“数据库操作”为 S。
- 不要把公司名、岗位名、学历、城市、薪资标为技能。
- 不要输出原文中没有证据的技能。
```

## User Prompt Template

```text
请对以下文本进行 L/S/K/T/Tech 能力标注。

输入信息：
doc_type: {jd_or_resume}
record_id: {record_id}
source_field: {source_field}
text:
{text}

可选标准实体表：
{entity_catalog_if_available}

输出要求：
1. 只输出 JSON，不要输出解释文字。
2. JSON 必须符合 schema。
3. 每个 annotation 必须包含 evidence_quote。
4. evidence_quote 必须是原文中的短句或片段。
5. 如果能链接到标准实体表，填写 entity_id；否则 entity_id 为 null，并设置 is_new_entity_candidate=true。
6. 不要输出 confidence < 0.60 的结果。
```

## Output JSON Schema

```json
{
  "record_id": "...",
  "doc_type": "jd | resume",
  "source_field": "...",
  "annotations": [
    {
      "mention": "原文中的能力词",
      "normalized_name": "标准化名称",
      "category": "Tech | S | K | T | L",
      "relation_type": "REQUIRES_TECHNOLOGY | REQUIRES_SKILL | REQUIRES_KNOWLEDGE | REQUIRES_TRANSVERSAL | REQUIRES_LANGUAGE | HAS_TECHNOLOGY | HAS_SKILL | HAS_KNOWLEDGE | HAS_TRANSVERSAL | HAS_LANGUAGE",
      "role": "required | preferred | mentioned | owned | used",
      "entity_id": "标准实体ID或null",
      "is_new_entity_candidate": true,
      "confidence": 0.0,
      "evidence_quote": "原文证据片段",
      "source_field": "...",
      "reason": "简短说明为什么这样分类"
    }
  ]
}
```

## JD 标注示例

输入：

```text
doc_type: jd
record_id: jd_001
source_field: requirements
text:
熟悉 Python、Linux、MySQL，有接口自动化测试经验，具备良好的沟通能力。熟悉 Selenium 者优先。
```

输出：

```json
{
  "record_id": "jd_001",
  "doc_type": "jd",
  "source_field": "requirements",
  "annotations": [
    {
      "mention": "Python",
      "normalized_name": "Python",
      "category": "Tech",
      "relation_type": "REQUIRES_TECHNOLOGY",
      "role": "required",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.98,
      "evidence_quote": "熟悉 Python、Linux、MySQL",
      "source_field": "requirements",
      "reason": "Python 是编程语言，属于技术栈，岗位明确要求熟悉"
    },
    {
      "mention": "接口自动化测试",
      "normalized_name": "接口自动化测试",
      "category": "S",
      "relation_type": "REQUIRES_SKILL",
      "role": "required",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.96,
      "evidence_quote": "有接口自动化测试经验",
      "source_field": "requirements",
      "reason": "接口自动化测试是岗位专业技能"
    },
    {
      "mention": "沟通能力",
      "normalized_name": "沟通能力",
      "category": "T",
      "relation_type": "REQUIRES_TRANSVERSAL",
      "role": "required",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.92,
      "evidence_quote": "具备良好的沟通能力",
      "source_field": "requirements",
      "reason": "沟通能力是通用能力"
    },
    {
      "mention": "Selenium",
      "normalized_name": "Selenium",
      "category": "Tech",
      "relation_type": "REQUIRES_TECHNOLOGY",
      "role": "preferred",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.95,
      "evidence_quote": "熟悉 Selenium 者优先",
      "source_field": "requirements",
      "reason": "Selenium 是测试自动化工具，且原文表示优先"
    }
  ]
}
```

## Resume 标注示例

输入：

```text
doc_type: resume
record_id: resume_R001
source_field: projects
text:
在接口自动化测试平台项目中，使用 Python、Pytest、MySQL 完成测试脚本开发和报告生成，负责缺陷分析和问题定位。
```

输出：

```json
{
  "record_id": "resume_R001",
  "doc_type": "resume",
  "source_field": "projects",
  "annotations": [
    {
      "mention": "接口自动化测试",
      "normalized_name": "接口自动化测试",
      "category": "S",
      "relation_type": "HAS_SKILL",
      "role": "used",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.95,
      "evidence_quote": "在接口自动化测试平台项目中",
      "source_field": "projects",
      "reason": "项目经历中明确体现接口自动化测试能力"
    },
    {
      "mention": "Python",
      "normalized_name": "Python",
      "category": "Tech",
      "relation_type": "HAS_TECHNOLOGY",
      "role": "used",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.98,
      "evidence_quote": "使用 Python、Pytest、MySQL",
      "source_field": "projects",
      "reason": "Python 是技术栈，且在项目中使用"
    },
    {
      "mention": "缺陷分析",
      "normalized_name": "缺陷分析",
      "category": "S",
      "relation_type": "HAS_SKILL",
      "role": "used",
      "entity_id": null,
      "is_new_entity_candidate": true,
      "confidence": 0.93,
      "evidence_quote": "负责缺陷分析和问题定位",
      "source_field": "projects",
      "reason": "缺陷分析是软件测试相关专业技能"
    }
  ]
}
```

## 建议产物

建议标注流程输出这些文件：

```text
annotations.jsonl
entity_candidates.jsonl
graph_nodes.jsonl
graph_edges.jsonl
sentence_annotations.jsonl
```

`annotations.jsonl` 每行一个 source field 的标注结果。

`entity_candidates.jsonl` 存储无法链接到标准实体表的新实体候选。

`graph_nodes.jsonl` 存储 Job、Candidate、AbilityEntity、Evidence 节点。

`graph_edges.jsonl` 存储 `REQUIRES_*`、`HAS_*`、`SUPPORTED_BY` 等边。

## 图谱落库映射

每条 annotation 转为一条能力边：

JD：

```text
job:{job_id} --REQUIRES_*--> ability_entity
```

Resume：

```text
candidate:{resume_id} --HAS_*--> ability_entity
```

每条 annotation 同时生成 evidence 节点：

```text
evidence:{record_id}:{evidence_id}
```

并生成支持边：

```text
ability_entity --SUPPORTED_BY--> evidence:{record_id}:{evidence_id}
```

边属性建议保留：

```json
{
  "record_id": "jd_001",
  "source_field": "requirements",
  "surface": "Python",
  "role": "required",
  "confidence": 0.98,
  "evidence_ids": ["ev_001"]
}
```

## 质量验收规则

- 每个 annotation 必须有 `evidence_quote`。
- `relation_type` 必须和 `doc_type`、`category` 一致。
- 编程语言必须归为 `Tech`，不能归为 `L`。
- 否定表达不得标为 required / owned。
- 不输出原文无证据的技能。
- 新实体候选必须 `entity_id=null` 且 `is_new_entity_candidate=true`。
- 标注结果需要能直接生成 `REQUIRES_*` / `HAS_*` / `SUPPORTED_BY` 图谱边。

