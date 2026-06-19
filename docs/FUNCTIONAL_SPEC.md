# JD简历匹配系统 - 功能说明文档

> 版本: v0.1.0 (Demo 阶段)
> 更新日期: 2026-06-19

---

## 一、系统概述

本系统是一个**基于规则的新一代信息技术岗位能力图谱与人岗匹配平台**，面向人工智能、大数据、智能系统、物联网等数字经济领域。系统核心能力包括：JD/简历解析、人岗匹配诊断、岗位能力图谱构建、新岗位发现与既有岗位能力更新分析。

### 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    前端展示层                        │
│  Vue3 + Element Plus (JD_web) / 原生 HTML (frontend) │
├─────────────────────────────────────────────────────┤
│                    API 接口层                        │
│              FastAPI (Python)                       │
├──────────┬──────────┬──────────┬────────────────────┤
│ JD解析   │ 简历解析 │ 人岗匹配 │ 图谱/演化/管理      │
├──────────┴──────────┴──────────┴────────────────────┤
│                  算法引擎层                          │
│  JD解析器 | 简历解析器 | 匹配器 | 差距分析 | 图谱构建│
├─────────────────────────────────────────────────────┤
│                  数据层                              │
│  技能词表(100+技能) | 样例数据 | SQLite(可选)       │
└─────────────────────────────────────────────────────┘
```

---

## 二、功能模块详解

### 模块一：JD 智能解析

**功能描述**: 将非结构化的岗位描述（JD）文本解析为结构化的岗位能力画像。

**入口**: 前端「JD解析」页面 (`/jd-parse`) 或 API `POST /parse/jd`

#### 解析能力

| 能力项 | 说明 |
|--------|------|
| **岗位名称识别** | 从文本中自动提取岗位名称，如"大模型算法工程师" |
| **岗位分类** | 自动归类为算法岗/后端开发岗/数据岗/前端开发岗等 |
| **职责提取** | 从岗位职责区块逐条提取工作职责 |
| **任职要求拆解** | 从任职要求区块提取学历要求、经验年限、行业背景 |
| **技能抽取** | 基于技能词表+别名映射+上下文规则抽取所有技能点 |
| **技能权重计算** | 根据来源区块（任职要求/岗位职责/加分项）和强度词（精通/熟练/了解）计算权重 |
| **加分项识别** | 单独标记非必需但加分的技能 |

#### 技能类型体系（7 大类）

| 类型 | 示例技能（部分） |
|------|-----------------|
| 编程语言 | Python, Java, C++, Go, JavaScript, TypeScript, SQL, R, Scala, Shell |
| 框架工具 | PyTorch, TensorFlow, Spark, Docker, Kubernetes, Spring Boot, Vue, React, FastAPI, LangChain, Milvus, Elasticsearch, Redis, MySQL, Neo4j... |
| 算法能力 | 机器学习, 深度学习, 推荐算法, NLP, 计算机视觉, 知识图谱, 大语言模型, RAG, 召回模型, 排序模型 |
| 数据能力 | SQL, 数据分析, 数据挖掘, 数据仓库, ETL, 特征工程 |
| 工程能力 | 系统设计, 接口开发, 性能优化, 分布式系统, 微服务, CI/CD |
| 业务能力 | 用户增长, 风控, 供应链, 招聘业务, 企业服务, 知识库问答 |
| 通用能力 | 沟通协作, 项目管理, 文档能力, 学习能力 |

#### 输出结构

```json
{
  "job_title": "大模型算法工程师",
  "job_category": "算法岗",
  "responsibilities": ["负责企业知识库问答场景的大语言模型应用建设...", ...],
  "requirements": ["本科及以上学历, 3年以上NLP或大模型相关经验...", ...],
  "education_requirement": "本科",
  "experience_requirement": 3,
  "domain_requirement": ["企业服务", "知识库问答"],
  "skills": [
    {
      "name": "Python",
      "skill_type": "编程语言",
      "weight": 1.2,
      "requirement_level": "required",
      "evidence_texts": ["熟练掌握 Python"]
    }
  ],
  "skill_distribution": {"编程语言": 0.25, "框架工具": 0.30, ...}
}
```

---

### 模块二：简历智能解析

**功能描述**: 将简历文本（纯文本或文件上传）解析为结构化候选人能力画像。

**入口**: 前端「简历解析」页面 (`/resume-parse`) 或 API `POST /parse/resume` / `POST /parse/resume-document`

#### 支持的输入格式

| 格式 | 支持状态 | 说明 |
|------|---------|------|
| 纯文本 | 支持 | 直接粘贴或输入文本 |
| .txt 文件 | 支持 | UTF-8/GB18030 等多编码自动检测 |
| .md 文件 | 支持 | Markdown 格式 |
| .pdf 文件 | 支持 | 使用 pypdf 库提取文本 |
| .docx 文件 | 支持 | 使用 python-docx 库提取文本（含表格） |

#### 解析能力

| 能力项 | 说明 |
|--------|------|
| **候选人信息提取** | 姓名、求职意向 |
| **教育经历识别** | 学校、专业、学历层次、毕业时间 |
| **工作经历提取** | 公司、职位、时间范围、工作内容 |
| **项目经历提取** | 项目名称、角色、技术栈、产出成果 |
| **技能清单提取** | 显式技能声明（来自技能清单区块）|
| **隐式技能推断** | 从项目/工作经历中推断使用过的技术 |
| **证书/成果识别** | 证书、论文、专利、竞赛、开源贡献 |
| **熟练度评估** | 根据表达强度（精通/熟练/了解）+ 来源（工作/项目/清单）+ 时间新鲜度综合评分 |
| **领域经验识别** | 从行业关键词判断候选人的业务领域背景 |

#### 输出结构

```json
{
  "candidate_id": "张三",
  "target_position": "大模型算法工程师",
  "education": "硕士",
  "experience_years": 3.0,
  "work_experiences": ["2023.07-至今 XX科技 算法工程师...", ...],
  "projects": ["负责 RAG 检索增强生成链路开发...", ...],
  "domain_experiences": ["企业服务", "知识库问答"],
  "skills": [
    {
      "name": "Python",
      "proficiency": 0.9,
      "source_section": "work_experiences",
      "evidence_texts": ["使用 Python 开发推理服务接口"]
    }
  ]
}
```

---

### 模块三：人岗匹配诊断与差距分析（核心功能）

**功能描述**: 对比目标岗位（JD）与候选人（简历）的能力画像，输出匹配分数、命中技能、缺失技能、差距分析和改进建议。

**入口**: 前端「人岗匹配」页面 (`/matching`) 或 API `POST /match`

#### 输入方式

| 方式 | 说明 |
|------|------|
| **样例选择** | 从预置的 4 组 JD+简历样例中选择（大模型/推荐/后端/数据开发）|
| **历史记录回溯** | 选择之前保存过的匹配结果重新查看 |
| **手动文本输入** | 直接粘贴自定义的 JD 和简历文本进行实时匹配 |

#### 六维评分体系

| 维度 | 权重 | 计算方式 |
|------|------|---------|
| **技能覆盖率** | 50% | JD 核心技能被简历覆盖的程度（加权求和）|
| **分布相似度** | 20% | JD 与简历技能向量之间的余弦相似度 |
| **经验匹配** | 10% | 工作年限是否满足 JD 要求 |
| **学历匹配** | 8% | 学历是否满足或高于要求 |
| **领域匹配** | 7% | 行业/业务背景是否一致 |
| **语义匹配** | 5% | JD 职责与简历经历的语义相似度（Jaccard + 动词重叠）|

#### 硬性扣分机制

| 扣分条件 | 扣分值 |
|----------|--------|
| 核心必备技能缺失 ≥2 个 | -20 分 |
| 年限严重不足（差距 >2年）| -15 分 |
| 学历硬门槛不满足 | -10 分 |
| 岗位方向明显不一致 | -10 分 |

#### 匹配结果输出

```json
{
  "final_score": 78.5,
  "dimension_scores": {
    "skill_coverage": 0.82,
    "distribution_similarity": 0.75,
    "experience_fit": 1.0,
    "education_fit": 1.0,
    "domain_fit": 1.0,
    "semantic_fit": 0.68
  },
  "matched_skills": [
    {
      "name": "Python",
      "match_type": "exact",
      "contribution": 1.08,
      "evidence_from_jd": ["熟练掌握 Python"],
      "evidence_from_resume": ["使用 Python 开发推理服务接口"]
    }
  ],
  "missing_skills": [
    {
      "name": "Kubernetes",
      "priority": "medium",
      "jd_weight": 0.7,
      "evidence_from_jd": ["有 Kubernetes 经验优先"]
    }
  ],
  "insufficient_skills": [...],
  "explanation": "候选人与岗位在 Python、机器学习等核心技能上匹配度较高..."
}
```

#### 差距分析三类判定

| 类型 | 含义 | 示例 |
|------|------|------|
| **缺失 (missing)** | 简历中完全没有该技能的证据 | JD 要求 Kafka，简历未提及 |
| **不足 (insufficient)** | 有相关证据但熟练度不够 | JD 要求精通 Python，简历只写了解 |
| **相关 (related_only)** | 只有上位/下位/相关技能 | JD 要求 PyTorch，简历只有 TensorFlow |

#### 改进建议生成

系统根据缺失/不足技能自动生成针对性改进建议：
- 缺失技能 → 建议补充学习、项目或工作证据
- 不足技能 → 建议强化项目深度描述（职责、产出、指标）

---

### 模块四：岗位能力图谱

**功能描述**: 构建并可视化展示岗位-技能关系图谱。

**入口**: 前端「岗位图谱」页面 (`/position-graph`) 或 API `GET /graph/full`, `GET /graph/view`, `POST /graph/panorama`

#### 图谱节点类型

| 节点类型 | 说明 | 示例 |
|----------|------|------|
| Job | 岗位 | 大模型算法工程师 |
| Skill | 技能点 | Python, 机器学习 |
| SkillType | 技能类别 | 编程语言, 算法能力 |
| Domain | 领域 | 新一代信息技术 |
| Level | 级别 | 初级/中级/高级 |
| JobCategory | 岗位分类 | 算法岗, 后端开发岗 |

#### 图谱边类型

| 边类型 | 含义 | 权重含义 |
|--------|------|---------|
| requires | 岗位→技能：要求该技能 | 技能权重 (0.4~1.5) |
| belongs_to_category | 岗位→分类 | 固定 1.0 |
| has_level | 岗位→级别 | 固定 1.0 |
| belongs_to_skill_type | 技能→类型 | 固定 1.0 |
| related_to | 技能→技能：相关关系 | 固定 0.5 |
| contains_job | 领域→岗位 | 固定 1.0 |

#### 图谱视图模式（5 种）

| 视图模式 | 切换参数 | 说明 |
|----------|---------|------|
| **position 视图** | `view_type=position` | 以岗位为中心展示其要求的全部技能 |
| **tech_stack 视图** | `view_type=tech_stack` | 按技术栈分类展示技能分布 |
| **level 视图** | `view_type=level` | 按级别（初级/中级/高级）分组展示 |
| **match 视图** | `view_type=match` | 展示单次匹配结果的岗位-简历-技能关系 |
| **evolution 视图** | `view_type=evolution` | 展示岗位能力演化的变更对比 |

#### 全景图谱构建

支持输入多个岗位 JD 文本，构建跨岗位的全景能力图谱：

- 统计各技能在多少个岗位中出现（support_count）
- 计算技能的平均权重和最大权重
- 按技术栈和级别两个维度提供结构化视图
- 内置技能间相关关系边（如 Python ↔ 机器学习, Spring Boot ↔ 微服务）

---

### 模块五：新岗位发现与定义

**功能描述**: 聚合多个来源的类 JD 文本，通过交叉验证发现萌芽中的新兴岗位并生成草稿定义。

**入口**: API `POST /evolution/discover` 或 `POST /jobs/discover`

#### 发现流程

```
输入: 多个来源的 JD 类文本（含 source_id, source_type, reliability）
  ↓
逐条解析每个源文档 → 提取岗位名称/类别/职责/技能
  ↓
聚合统计:
  - 岗位名称投票 → 最可能的岗位名
  - 技能出现频次 + 来源可靠性加权 → 核心技能 vs 加分技能
  - 职责/场景出现频次 → 核心职责 + 典型行业场景
  ↓
输出: 新兴岗位草稿定义（含置信度评分）
```

#### 输出字段

| 字段 | 说明 |
|------|------|
| job_title | 聚合得到的岗位名称 |
| job_category | 归属岗位类别 |
| core_responsibilities | 核心职责（Top 6）|
| required_skills | 必备技能（按 cross_source_score 排序 Top 10）|
| preferred_skills | 加分技能（Top 8）|
| typical_industry_scenarios | 典型行业场景 |
| source_count | 聚合的源文档数量 |
| confidence | 发现置信度 (0~1) |

#### 幻觉防控机制

- 所有生成的技能均来自**已解析的原文证据**，不凭空捏造
- 多源支持的技能排名更高（cross_source_score = weight × support_count × avg_reliability）
- 只出现一次的低可靠性提及会被降权

---

### 模块六：既有岗位能力动态更新

**功能描述**: 对比同一岗位新旧两个版本的 JD，精确识别能力项的增删改变化。

**入口**: API `POST /evolution/update` 或 `POST /jobs/compare`

#### 更新分析输出

| 变更类型 | 字段 | 说明 |
|----------|------|------|
| **新增 (added)** | added_skills | 新版有、旧版无的能力项 |
| **删除 (removed)** | removed_skills | 旧版有、新版无的能力项 |
| **修改 (modified)** | modified_skills | 两版都有但权重/等级发生变化的能力项 |

每条变更记录包含：
- skill_id / name / skill_type
- 权重变化 (old_weight → new_weight, delta)
- 等级变化 (old_level → new_level)
- 来源证据 (new_evidence)

#### 更新摘要

自动生成自然语言摘要，例如：
> "新增能力: 大语言模型、RAG；弱化/删除能力: 传统搜索引擎优化；权重变化能力: Python"

---

### 模块七：后台管理（技能 & 岗位 CRUD）

**功能描述**: 提供技能库和岗位库的管理接口，支持增删改查操作。

#### 技能管理 API (`/skills`)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/skills` | 获取所有技能（支持类别筛选/关键词搜索）|
| GET | `/skills/categories` | 获取所有技能类别列表 |
| GET | `/skills/{id}` | 获取技能详情 |
| POST | `/skills` | 创建新技能（含级别/可靠性评分）|
| POST | `/skills/batch` | 批量创建技能（用于初始化技能库）|
| PUT | `/skills/{id}` | 更新技能信息 |
| DELETE | `/skills/{id}` | 软删除技能（标记为废弃）|

#### 岗位管理 API (`/positions`)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/positions` | 获取所有有效岗位 |
| GET | `/positions/new` | 获取新发现的待确认岗位 |
| GET | `/positions/{id}` | 获取岗位详情 |
| POST | `/positions` | 创建新岗位（可标记为新岗位）|
| PUT | `/positions/{id}` | 更新岗位信息 |
| DELETE | `/positions/{id}` | 软删除岗位（归档）|
| POST | `/positions/{id}/confirm` | 确认新岗位为标准岗位 |
| GET | `/positions/{id}/skills` | 获取岗位关联的所有技能 |
| POST | `/positions/{id}/skills` | 为岗位添加技能关联 |

---

## 三、前端页面导航

| 页面 | 路由 | 功能 |
|------|------|------|
| **首页** | `/` | 功能总览卡片导航 |
| **JD 解析** | `/jd-parse` | 输入 JD 文本/上传文件 → 解析结果展示 |
| **简历解析** | `/resume-parse` | 输入简历文本/上传 PDF/Word → 解析结果展示 |
| **人岗匹配** | `/matching` | 选择样例/手动输入/历史记录 → 匹配诊断结果 |
| **岗位图谱** | `/position-graph` | 全景图谱/局部图谱可视化展示 |

---

## 四、完整 API 接口列表

### 基础接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/samples` | 获取预置样例数据（JD + 简历）|

### 解析接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/parse/jd` | 解析 JD 文本 |
| POST | `/parse/resume` | 解析简历文本 |
| POST | `/parse/resume-document` | 上传并解析简历文件（PDF/Word/TXT/MD）|

### 匹配接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/match` | 执行人岗匹配诊断 |

### 图谱接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/graph/full` | 获取完整岗位-技能图谱 |
| GET | `/graph/view?view_type=` | 按指定视图获取图谱（position/tech_stack/level/match/evolution）|
| POST | `/graph/panorama` | 构建全景多岗位图谱 |

### 演化接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/evolution/discover` | 新岗位发现 |
| POST | `/evolution/update` | 岗位能力更新对比 |
| POST | `/jobs/discover` | （同 discover 别名）|
| POST | `/jobs/compare` | （同 update 别名）|

### 管理接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET/POST/PUT/DELETE | `/skills/*` | 技能 CRUD（见上方详细表格）|
| GET/POST/PUT/DELETE | `/positions/*` | 岗位 CRUD（见上方详细表格）|

---

## 五、算法引擎组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **JD 解析器** | [jd_parser.py](backend/app/algorithms/jd_parser.py) | JD 文本预处理 → 区块识别 → 技能抽取 → 权重计算 |
| **简历解析器** | [resume_parser.py](backend/app/algorithms/resume_parser.py) | 简历文本预处理 → 区块识别 → 技能抽取 → 熟练度评估 |
| **技能抽取器** | [skill_extractor.py](backend/app/algorithms/skill_extractor.py) | 基于词表+别名映射的技能识别与标准化 |
| **技能词表** | [skill_catalog.py](backend/app/algorithms/skill_catalog.py) | 100+ 标准技能定义、别名映射、技能间关系 |
| **匹配器** | [matcher.py](backend/app/algorithms/matcher.py) | 六维加权评分 + 硬性扣分 + 技能级匹配逻辑 |
| **差距分析器** | [gap_analyzer.py](backend/app/algorithms/gap_analyzer.py) | 缺失/不足/相关三类差距判定 + 改进建议生成 |
| **图谱构建器** | [panorama_graph.py](backend/app/algorithms/panorama_graph.py) | 多岗位全景图谱构建 + 5 种视图切分 |
| **岗位情报分析** | [job_intelligence.py](backend/app/algorithms/job_intelligence.py) | 新岗位聚合发现 + 岗位版本对比 |
| **文本规则** | [text_rules.py](backend/app/algorithms/text_rules.py) | 学历/年限/领域/区块标题的正则规则集 |
| **归一化器** | [normalizer.py](backend/app/algorithms/normalizer.py) | 文本清洗、标点统一、别名归一化 |
| **画像构建器** | [profile_builder.py](backend/app/algorithms/profile_builder.py) | 将原始解析结果组装为标准 SkillProfile |
| **图谱适配器** | [graph_adapter.py](backend/app/algorithms/graph_adapter.py) | 匹配结果转图谱节点/边的适配层 |
| **模型适配器** | [model_adapter.py](backend/app/algorithms/model_adapter.py) | LLM 增强模式的适配层（预留扩展）|
| **文档解析** | [document_text.py](backend/app/input_adapters/document_text.py) | PDF(pypdf)/DOCX(python-docx)/TXT/MD 文件转文本 |

---

## 六、数据流示意

```
用户输入 JD 文本 ──→ JD 解析器 ──→ 岗位能力画像 (JobProfile)
                                              │
用户输入简历文本 ──→ 简历解析器 ──→ 候选人能力画像 (ResumeProfile)
                                              │
                                    ┌─────────▼──────────┐
                                    │   RuleBasedMatcher   │
                                    │  (六维加权评分引擎)   │
                                    └─────────┬──────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                   MatchResult          GapAnalyzer         GraphAdapter
                   (匹配分数+维度)      (差距分析)           (图谱节点/边)
                         │                    │                    │
                         ▼                    ▼                    ▼
                   前端匹配结果页        改进建议            图谱可视化
```

---

## 七、当前完成情况与待完善项


### 已完成（用户可实际使用）

#### 一、JD 智能解析 — 前端页面 + 后端接口完整可用

- **前端页面**：[JdParseView.vue](JD_web/src/views/JdParseView.vue)（路由 `/jd-parse`）
- **后端接口**：`POST /parse/jd`
- **功能**：
  - 文本输入模式：粘贴或输入 JD 文本，点击"开始解析"
  - 文件上传模式：支持 TXT / JSON / CSV / Excel 格式，可多选批量导入
  - 解析结果展示：职位名称、岗位类别、经验要求、学历要求、必需技能标签、优选技能标签、岗位职责列表、岗位要求列表、解析置信度进度条
  - 批量解析支持：多文件依次解析，结果翻页浏览（上一条/下一条）
  - 历史解析记录列表（底部表格）

#### 二、简历智能解析 — 前端页面 + 后端接口完整可用

- **前端页面**：[ResumeParseView.vue](JD_web/src/views/ResumeParseView.vue)（路由 `/resume-parse`）
- **后端接口**：`POST /parse/resume`（文本）、`POST /parse/resume-document`（PDF/Word文件）
- **功能**：
  - 文本输入模式：粘贴或输入简历文本
  - 文件上传模式：支持 PDF / Word(.doc/.docx) / TXT 格式，可多选批量导入（PDF和Word通过base64编码传给后端）
  - 解析结果展示：候选人信息（学历、工作年限）、专业技能标签、教育经历时间线、工作经历时间线（含职责列表）、项目经历（含技术栈标签）
  - 批量解析支持：多文件依次解析，结果翻页浏览
  - 历史解析记录列表（底部表格）具体接口还未完成

#### 三、人岗匹配诊断与差距分析 — 前端页面 + 后端接口完整可用

- **前端页面**：[MatchingView.vue](JD_web/src/views/MatchingView.vue)（路由 `/matching`）
- **后端接口**：`POST /match`
- **功能**：
  - 三种输入方式：样例选择（预置4组JD+简历）/ 历史记录（从已解析的JD和简历中选择）/ 手动文本输入（直接粘贴JD和简历文本）
  - 匹配结果展示：总匹配分数、六维雷达图（技能覆盖度/分布相似度/经验匹配度/学历匹配度/领域相关度/语义关联度）
  - 差距分析：缺失技能（红色）/ 不足技能（橙色）/ 相关技能（灰色）三类分类表格，每项带权重和证据来源
  - 改进建议：针对每类差距给出具体建议
  - 支持勾选"使用LLM增强分析"

#### 四、岗位能力图谱查看 — 前端页面 + 后端接口完整可用

- **前端页面**：[PositionGraphView.vue](JD_web/src/views/PositionGraphView.vue)（路由 `/position-graph`）
- **后端接口**：`GET /graph/full`、`GET /graph/view`、`POST /graph/panorama`
- **功能**：
  - 岗位列表选择（左侧下拉框）
  - 选中岗位的技能详情展示（技能名称/类型分类/重要程度/是否必修）
  - 按技术栈视图切换：按技能类型分组显示（编程语言/框架工具/算法能力等）
  - 按级别视图切换：核心要求/进阶要求/基础要求三级分组显示
  - ECharts 关系图可视化

#### 五、首页导航

- **前端页面**：[HomeView.vue](JD_web/src/views/HomeView.vue)（路由 `/`）
- **功能**：系统介绍 + 4个功能入口卡片（JD解析 / 简历解析 / 人岗匹配 / 岗位图谱），点击跳转对应页面

#### 六、顶部导航栏

- **组件**：[Header.vue](JD_web/src/components/Header.vue)
- **导航项**：首页 | JD解析 | 简历解析 | 人岗匹配 | 岗位图谱（共5个入口，无"新岗位发现"和"既有岗位更新"入口）

---

### 后端已有但前端未对接（用户无法通过界面使用）

| 后端接口 | 功能 | 说明 |
|----------|------|------|
| `POST /evolution/discover`（别名 `POST /jobs/discover`）| 新岗位发现与定义 | 接受多条JD文本，聚合生成新岗位草稿定义。**无前端页面，用户无法操作** |
| `POST /evolution/update`（别名 `POST /jobs/compare`）| 既有岗位能力动态更新 | 接受新旧两版JD，比对差异输出新增/删除/修改的能力项。**无前端页面，用户无法操作** |
| `GET /samples` | 获取内置样例数据 | 返回4条JD样例和4条简历样例。被JD解析页和简历解析页内部调用 |

---

### 未完成 / 待开发

#### 核心功能缺口

| 缺失项 | 对应竞赛要求 | 当前状态 |
|--------|-------------|---------|
| 新岗位发现与定义（完整功能含前端） | 功能① | 后端API有，**前端页面未开发**，导航栏无入口 |
| 既有岗位能力动态更新（完整功能含前端） | 功能② | 后端API有，**前端页面未开发**，导航栏无入口 |
| 学习路径规划 | 功能④子项 | 数据库表未建，**无任何实现代码** |
| 主动发现算法（聚类/标准库比对/趋势检测）| 功能①深化 | 后端仅为被动聚合模式 |

#### 创新性缺口

| 缺失项 | 对应竞赛要求 | 说明 |
|--------|-------------|------|
| 时滞检测 | 创新① | 无 |
| 抄袭/模板检测 | 创新① | 无 |
| 通胀识别 | 创新① | 无 |
| LLM 输出事实核查 | 创新② | 无 |
| 外部知识库比对 | 创新② | 无 |

#### 可验证性缺口（最紧急）

| 缺失项 | 要求 | 当前状态 |
|--------|------|---------|
| JD 测试样本 | ≥100 条 | 仅4条内置样例 |
| 简历测试样本 | 配套数量 | 仅4条内置样例 |
| 金标准标注 | 用于计算准确率 | 无 |
| JD 解析准确率 | ≥90% | 无法验证 |
| 简历提取准确率 | ≥90% | 无法验证 |
| 匹配准确率 | ≥90% | 无法验证 |
| 自动化测试套件 | 完整测试方案 | 仅有手动测试脚本 |

---

### 总结

目前系统已具备 **JD 智能解析、简历智能解析、人岗匹配诊断、岗位图谱查看** 四大核心功能的完整前后端链路（前端页面 + 后端算法 + API 接口），用户可通过界面正常操作使用。**新岗位发现**与**既有岗位能力更新**的后端接口已开发完成，但缺少对应的前端页面和导航入口，用户暂无法通过界面操作。

**尚未实现的功能包括：** 学习路径规划模块、主动发现算法（聚类/标准库比对/趋势检测）、时滞/抄袭/通胀数据清洗机制、幻觉防控校验机制。

**可验证性方面：** 测试样本仅 4 条（要求 ≥100 条），JD 解析准确率、简历提取准确率、匹配准确率三项 ≥90% 指标均因缺少金标准标注而无法验证，自动化测试方案尚不完整。上述内容为后续开发的重点方向。
