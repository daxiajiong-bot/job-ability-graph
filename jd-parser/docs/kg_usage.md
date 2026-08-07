# 9000 条 JD 知识图谱构建与使用说明

本文说明如何从已经抽取好的 9000 条 JD Profile 构建岗位能力知识图谱，并查看有效性检测结果和网页可视化。

## 1. 输入文件

默认输入为：

```text
jd-parser/data/output/real_9000/profiles.jsonl
```

该文件每行是一条 `jd_profile_v1` 结构化岗位数据，核心字段包括：

- `document_id`
- `title`
- `skills`
- `constraints.education`
- `constraints.experience_years`
- `constraints.location`
- `raw_text`

知识图谱只使用这些已经抽取出的事实，不额外补充原文中不存在的信息。

## 2. 构建知识图谱

在项目根目录执行：

```powershell
cd D:\vs\job-ability-graph\jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli kg --profiles data\output\real_9000\profiles.jsonl --output data\output\kg_real_9000 --sample-jobs 5
```

也可以使用封装脚本：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\build_kg.py
```

构建后输出目录为：

```text
jd-parser/data/output/kg_real_9000/
```

## 3. 图谱 Schema

### 节点类型

| 节点 | 含义 |
| --- | --- |
| `Job` | 岗位节点 |
| `Skill` | 技能节点，保留原始技能名称 |
| `Evidence` | 原文证据节点 |
| `Education` | 学历要求节点 |
| `ExperienceRequirement` | 最低经验年限节点 |
| `Location` | 工作地点节点 |

### 关系类型

| 关系 | 含义 |
| --- | --- |
| `REQUIRES_SKILL` | 岗位必需技能 |
| `PREFERS_SKILL` | 岗位优先/加分技能 |
| `MENTIONS_SKILL` | 岗位职责或场景中提到的相关技能 |
| `SUPPORTED_BY` | 技能或约束由某条原文证据支持 |
| `REQUIRES_EDUCATION` | 岗位学历要求 |
| `REQUIRES_EXPERIENCE` | 岗位经验要求 |
| `LOCATED_IN` | 岗位工作地点 |

技能关系由 `skill.level` 决定：

```text
required  -> REQUIRES_SKILL
preferred -> PREFERS_SKILL
mentioned -> MENTIONS_SKILL
```

## 4. 主要输出文件

| 文件 | 用途 |
| --- | --- |
| `graph_nodes.jsonl` | 图谱节点 |
| `graph_edges.jsonl` | 图谱边 |
| `graph_summary.json` | 节点数、边数、覆盖率、Top Skills |
| `validation_report.json` | 有效性检测结果 |
| `top_skills.csv` | 高频技能统计 |
| `sample_subgraph_first_5.json` | 前 5 个岗位的局部子图 |
| `sample_subgraph_first_5.md` | 前 5 个岗位的表格化展示 |
| `sample_subgraph_first_5.html` | 前 5 个岗位的简易 HTML 展示 |
| `web/index.html` | 交互式网页可视化入口 |

## 5. 查看有效性检测

打开：

```text
jd-parser/data/output/kg_real_9000/validation_report.json
```

重点看这些字段：

| 字段 | 含义 |
| --- | --- |
| `status` | 图谱整体状态，`valid` 表示结构有效 |
| `duplicate_node_ids` | 重复节点 ID 数 |
| `duplicate_edge_ids` | 重复边 ID 数 |
| `invalid_node_labels` | 非法节点类型数 |
| `invalid_relation_types` | 非法关系类型数 |
| `dangling_edges` | 悬空边数量 |
| `evidence_text_missing_from_raw_text` | 证据无法在原文中找到的数量 |
| `jobs_without_skill_edges` | 未抽到技能边的岗位数量 |
| `isolated_node_count` | 孤立节点数量 |

当前结果中，图谱状态为 `valid`。如果出现 `errors`，需要先修复抽取结果或构图规则后再用于下游模型。

## 6. 查看网页可视化

先生成网页数据：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\build_kg_web.py
```

然后直接打开：

```text
jd-parser/data/output/kg_real_9000/web/index.html
```

网页支持：

- 查看全局节点数、边数、覆盖率；
- 查看 Top 技能关系；
- 查看前 5 个岗位局部子图；
- 输入技能名称查看技能聚焦子图；
- 查看技能样例岗位和原文证据；
- 查看有效性检测摘要。

## 7. 构建流程图

流程图文件：

```text
jd-parser/docs/kg_build_flow.md
```

核心流程：

```text
profiles.jsonl
-> 创建 Job 节点
-> 创建 Skill / Evidence / Education / Experience / Location 节点
-> 创建岗位-技能、岗位-约束、证据支持关系
-> 写出 graph_nodes.jsonl 和 graph_edges.jsonl
-> 运行有效性检测
-> 生成统计、局部子图和网页可视化
```

## 8. 如何用于人岗匹配

图谱可作为人岗匹配模型的岗位侧特征层。

推荐流程：

1. 将简历解析成候选人 Profile。
2. 从候选人 Profile 中抽取技能、学历、经验、地点。
3. 从岗位图谱中读取目标岗位的：
   - `REQUIRES_SKILL`
   - `PREFERS_SKILL`
   - `MENTIONS_SKILL`
   - `REQUIRES_EDUCATION`
   - `REQUIRES_EXPERIENCE`
   - `LOCATED_IN`
4. 计算匹配特征：
   - 必需技能命中率；
   - 优先技能命中率；
   - 缺失必需技能；
   - 学历是否满足；
   - 经验是否满足；
   - 地点是否匹配；
   - 匹配证据路径。
5. 输出匹配分、缺失技能和解释。

一个简单可解释公式：

```text
score =
  0.45 * required_skill_hit_ratio
+ 0.15 * preferred_skill_hit_ratio
+ 0.15 * experience_fit
+ 0.10 * education_fit
+ 0.10 * location_fit
+ 0.05 * evidence_coverage
```

其中：

- `required_skill_hit_ratio`：候选人命中的必需技能数 / 岗位必需技能数；
- `preferred_skill_hit_ratio`：候选人命中的优先技能数 / 岗位优先技能数；
- `experience_fit`：候选人经验年限是否达到岗位最低要求；
- `education_fit`：候选人学历是否达到岗位要求；
- `location_fit`：候选人期望地点是否匹配岗位地点；
- `evidence_coverage`：匹配项是否能回溯到岗位证据。

## 9. 知识抽取效果指标检测与 RAG 判断

本项目新增了自动化知识抽取效果评估，用于回答两个问题：

1. 当前 JD 知识抽取效果是否稳定；
2. 是否需要在抽取过程中引入 RAG。

### 9.1 运行评估

默认评估 9000 条真实 JD：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\evaluate_extraction.py
```

也可以手动指定路径：

```powershell
python scripts\evaluate_extraction.py `
  --profiles data\output\real_9000\profiles.jsonl `
  --validation-results data\output\real_9000\validation_results.jsonl `
  --output-dir data\output\extraction_eval_real_9000
```

输出：

```text
data/output/extraction_eval_real_9000/extraction_eval.json
data/output/extraction_eval_real_9000/extraction_eval.md
```

### 9.2 指标含义

| 指标 | 含义 |
| --- | --- |
| `title_coverage` | 有岗位名称的比例 |
| `skill_coverage` | 至少抽到一个技能的岗位比例 |
| `required_skill_doc_coverage` | 有必需技能的岗位比例 |
| `preferred_skill_doc_coverage` | 有优先技能的岗位比例 |
| `education_coverage` | 有学历要求的岗位比例 |
| `experience_coverage` | 有经验年限要求的岗位比例 |
| `location_coverage` | 有地点信息的岗位比例 |
| `avg_skills_per_doc` | 平均每条岗位抽取出的技能数量 |
| `skill_evidence_support_rate` | 技能证据可回溯到原文的比例 |
| `constraint_evidence_support_rate` | 学历/经验/地点证据可回溯到原文的比例 |
| `lexicon_recall_proxy` | 用当前技能词表复扫 raw_text 得到的召回代理指标 |
| `docs_with_candidate_but_no_skill_ratio` | 原文含候选技能词但 Profile 无技能的岗位比例 |
| `docs_with_low_skill_density_ratio` | 技能数小于等于 1 的岗位比例 |

注意：这些是无人工标注情况下的自动代理指标。如果要严格证明比赛要求中的“JD 解析准确率 ≥90%”，仍需要人工金标数据计算 precision、recall 和 F1。

### 9.3 是否需要加入 RAG

评估脚本会输出：

```json
{
  "rag_recommendation": {
    "mode": "...",
    "reasons": [],
    "recommended_strategy": []
  }
}
```

判定逻辑：

- 如果证据支持率低于 99%，不建议马上加入 RAG，应先修复证据校验；
- 如果技能覆盖率低于 95%，建议用 RAG 检索术语词表或相似 JD 样例提升召回；
- 如果 `lexicon_recall_proxy` 低于 90%，说明可能存在明显漏抽，建议引入检索增强词表；
- 如果低技能密度岗位较多，可选用 RAG 检索相似岗位样例辅助抽取；
- 如果当前证据支持率和覆盖率较高，RAG 不应替代抽取器，只适合作为候选术语和归一化辅助。

推荐的 RAG 使用方式：

- 检索技能词表、岗位族样例、人工标注样例；
- RAG 返回的候选技能必须再次在 `raw_text` 中命中；
- 不允许把 RAG 检索结果直接写入 Profile；
- 更建议把 RAG 放在技能归一化、岗位族对齐和人岗匹配解释阶段。

### 9.4 当前已引入的 RAG 实现

当前实现的是本地 RAG，不调用外部 LLM，也不依赖外部向量数据库。

核心策略：

```text
已有 Profile
-> 构建本地技能检索索引
-> 对每条 JD 检索候选技能
-> 候选技能必须在当前 raw_text 中出现
-> 找到原文证据句
-> 根据证据句判断 required / preferred / mentioned
-> 写入增强版 Profile
```

运行：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\run_rag_augmentation.py
```

输出目录：

```text
data/output/rag_real_9000/
```

主要输出：

- `profiles.jsonl`：RAG 增强后的 Profile；
- `validation_results.jsonl`：增强后校验结果；
- `serialized.jsonl`：增强后的模板序列化文本；
- `rag_added_skills.jsonl`：每条 JD 新增了哪些技能及证据；
- `retrieval_index_summary.json`：本地检索索引摘要；
- `summary.json`：增强统计。

如果要基于 RAG 增强结果重建知识图谱：

```powershell
cd D:\vs\job-ability-graph\jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli kg --profiles data\output\rag_real_9000\profiles.jsonl --output data\output\kg_rag_real_9000 --sample-jobs 5
python scripts\build_kg_web.py --kg-dir data\output\kg_rag_real_9000 --profiles data\output\rag_real_9000\profiles.jsonl --output data\output\kg_rag_real_9000\web
```

## 10. 代码使用说明

本节说明本流程中用到的主要代码文件：每个文件做什么、输入什么、输出什么，以及怎么运行。

### 10.1 `scripts/prepare_real_jd.py`

作用：从原始 JD 压缩包中读取 JD 数据，剔除已采样的 1000 个 `job_id`，按原始顺序取剩余数据中的前 9000 条，生成标准批处理输入。

输入：

- `jd_raw_10000.zip`
- `jd_1000_job_ids.txt`

输出：

- `data/input/jd_remaining_9000.jsonl`
- `data/input/jd_remaining_9000_source_records.jsonl`
- `data/input/jd_remaining_9000_summary.json`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\prepare_real_jd.py `
  --zip "D:\xwechat_files\wxid_r9xfhwvpziry22_1cbc\msg\file\2026-07\jd_raw_10000.zip" `
  --exclude-ids "D:\xwechat_files\wxid_r9xfhwvpziry22_1cbc\msg\file\2026-07\jd_1000_job_ids.txt" `
  --target-count 9000 `
  --output data\input\jd_remaining_9000.jsonl
```

### 10.2 `src/jd_parser/schemas.py`

作用：定义 JD 解析和校验用到的数据结构，保证输入输出字段稳定。

输入：

- Python 字典或 JSON 数据。

输出：

- `JDProfile`
- `Skill`
- `JDConstraints`
- `ValidationResult`
- `SerializedRecord`
- `BatchSummary`

使用方式：

```python
from jd_parser.schemas import JDProfile

profile = JDProfile.model_validate(raw_dict)
```

### 10.3 `src/jd_parser/cleaner.py`

作用：对原始 JD 文本做确定性清洗，去除重复空行、重复段落和明显网页导航噪声。

输入：

- 一段原始 JD 文本字符串。

输出：

- `cleaned_text` 字符串。

使用方式：

```python
from jd_parser.cleaner import clean_text

cleaned_text = clean_text(raw_text)
```

### 10.4 `src/jd_parser/extractor.py`

作用：从清洗后的 JD 文本中抽取岗位名称、职责、要求、优先项、技能、学历、经验、地点，形成 `JDProfile`。

输入：

- `document_id`
- `raw_text`

输出：

- `JDProfile`

使用方式：

```python
from jd_parser.extractor import RuleBasedExtractor

extractor = RuleBasedExtractor()
profile = extractor.extract("JD_001", raw_text)
```

说明：

- 当前实现为规则抽取器；
- 不调用外部 LLM API；
- 不做技能归一化；
- 技能必须来自原文证据。

### 10.5 `src/jd_parser/validator.py`

作用：校验 `JDProfile` 是否符合 Schema 和证据规则。

输入：

- `JDProfile` 或 Python 字典；
- 可选 `raw_text`；
- 可选 `cleaned_text`。

输出：

- `ValidationResult`

使用方式：

```python
from jd_parser.validator import validate_profile

result = validate_profile(profile, raw_text=raw_text, cleaned_text=cleaned_text)
```

主要检查：

- `document_id` 是否存在；
- `document_type` 是否为 `job`；
- `skills` 是否为数组；
- `skill.level` 是否只属于 `required / preferred / mentioned`；
- 每个技能是否有 `evidence`；
- evidence 是否能在原文中找到；
- 学历、经验、地点非空时是否有证据；
- 是否有重复技能；
- 是否出现 Schema 外字段。

### 10.6 `src/jd_parser/serializer.py`

作用：把 `JDProfile` 转成固定模板文本，便于人工阅读和审查。

输入：

- `JDProfile`

输出：

- 确定性 `serialized_text`

使用方式：

```python
from jd_parser.serializer import serialize_profile

text = serialize_profile(profile)
```

输出示例：

```text
[岗位名称]
NLP算法工程师

[必需技能]
Python；PyTorch
```

### 10.7 `src/jd_parser/batch.py`

作用：批量处理 JSONL 输入，完成清洗、抽取、校验、序列化，并保存审计文件。

输入：

- JSONL 文件，每行格式类似：

```json
{"document_id":"JD_001","raw_text":"岗位名称：NLP算法工程师..."}
```

输出：

- `profiles.jsonl`
- `validation_results.jsonl`
- `serialized.jsonl`
- `cleaned.jsonl`
- `raw_model_outputs.jsonl`
- `errors.jsonl`
- `summary.json`

使用方式：

```python
from pathlib import Path
from jd_parser.batch import BatchOptions, run_batch

summary = run_batch(
    BatchOptions(
        input_path=Path("data/input/jd_remaining_9000.jsonl"),
        output_dir=Path("data/output/real_9000"),
        force=True,
    )
)
```

命令行方式见 `src/jd_parser/cli.py`。

### 10.8 `src/jd_parser/cli.py`

作用：提供命令行入口，统一执行批处理和知识图谱构建。

输入：

- 命令行参数。

输出：

- 控制台 summary；
- 对应输出目录中的 JSONL、JSON、HTML 等文件。

批量抽取使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli batch --input data\input\jd_remaining_9000.jsonl --output data\output\real_9000 --force
```

构建知识图谱使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli kg --profiles data\output\real_9000\profiles.jsonl --output data\output\kg_real_9000 --sample-jobs 5
```

### 10.9 `src/jd_parser/kg.py`

作用：从 `profiles.jsonl` 构建知识图谱，并进行图谱有效性检测。

输入：

- `profiles.jsonl`
- 输出目录路径
- 局部子图岗位数量 `sample_jobs`

输出：

- `graph_nodes.jsonl`
- `graph_edges.jsonl`
- `graph_summary.json`
- `validation_report.json`
- `top_skills.csv`
- `sample_subgraph_first_5.json`
- `sample_subgraph_first_5.md`
- `sample_subgraph_first_5.html`

使用方式：

```python
from pathlib import Path
from jd_parser.kg import build_graph

summary = build_graph(
    Path("data/output/real_9000/profiles.jsonl"),
    Path("data/output/kg_real_9000"),
    sample_jobs=5,
)
```

核心规则：

- `Job` 节点来自每条 JD；
- `Skill` 节点来自 `profile.skills`；
- `Evidence` 节点来自每条技能或约束的原文证据；
- `Education / ExperienceRequirement / Location` 节点来自 `constraints`；
- 技能边由 `skill.level` 映射；
- 每个技能边保存 `evidence_id`，用于回溯原文。

### 10.10 `scripts/build_kg.py`

作用：封装默认路径，一键构建 9000 条 JD 知识图谱。

输入：

- `data/output/real_9000/profiles.jsonl`

输出：

- `data/output/kg_real_9000/`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\build_kg.py
```

### 10.11 `scripts/build_kg_web.py`

作用：从完整图谱输出中生成浏览器可加载的轻量网页数据包，并复制网页模板。

输入：

- `data/output/kg_real_9000/graph_summary.json`
- `data/output/kg_real_9000/validation_report.json`
- `data/output/kg_real_9000/top_skills.csv`
- `data/output/kg_real_9000/sample_subgraph_first_5.json`
- `data/output/real_9000/profiles.jsonl`

输出：

- `data/output/kg_real_9000/web/index.html`
- `data/output/kg_real_9000/web/assets/graph-data.js`
- `data/output/kg_real_9000/web/assets/app.js`
- `data/output/kg_real_9000/web/assets/styles.css`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\build_kg_web.py
```

如果要指定路径：

```powershell
python scripts\build_kg_web.py `
  --kg-dir data\output\kg_real_9000 `
  --profiles data\output\real_9000\profiles.jsonl `
  --output data\output\kg_real_9000\web
```

### 10.12 `web/index.html`

作用：交互式知识图谱网页入口。

输入：

- `assets/graph-data.js`
- `assets/app.js`
- `assets/styles.css`

输出：

- 浏览器中的图谱可视化界面。

使用：

```text
直接打开：
jd-parser/data/output/kg_real_9000/web/index.html
```

页面功能：

- 显示图谱统计；
- 展示 Top 技能图；
- 展示前 5 个岗位局部子图；
- 支持按技能聚焦查看岗位样例；
- 显示有效性检测摘要。

### 10.13 `web/assets/app.js`

作用：网页交互逻辑，包括视图切换、SVG 图谱绘制、节点详情、技能搜索、柱状图展示。

输入：

- `window.KG_WEB_DATA`，由 `graph-data.js` 提供。

输出：

- 页面上的交互式 SVG 图谱和统计组件。

使用：

- 不单独运行；
- 由 `web/index.html` 自动加载。

### 10.14 `web/assets/styles.css`

作用：网页样式文件，控制页面布局、颜色、图例、图谱节点和关系线样式。

输入：

- HTML 页面结构。

输出：

- 可视化页面样式。

使用：

- 不单独运行；
- 由 `web/index.html` 自动加载。

### 10.15 `scripts/build_review_report.py`

作用：生成用于人工审查的 Markdown 报告，展示原始 JD、清洗文本、Profile、校验状态和序列化文本。

输入：

- 批处理输入 JSONL；
- 批处理输出目录。

输出：

- Markdown 审查报告。

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\build_review_report.py `
  --input data\input\jd_remaining_9000.jsonl `
  --output-dir data\output\real_9000 `
  --report data\output\real_9000_review_first_100.md `
  --limit 100
```

### 10.16 `scripts/run_sample.py`

作用：运行 12 条自造 JD 测试样本，生成样本抽取结果和人工审查报告。

输入：

- `data/input/sample_12.jsonl`

输出：

- `data/output/sample_12/`
- `data/output/sample_12_review.md`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\run_sample.py
```

### 10.17 `tests/`

作用：单元测试目录，验证清洗、抽取、校验、序列化和知识图谱构建逻辑。

输入：

- 测试代码中的样例数据；
- 临时测试文件。

输出：

- 测试通过或失败信息。

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```

当前测试覆盖：

- `test_cleaner.py`
- `test_extractor.py`
- `test_validator.py`
- `test_serializer.py`
- `test_kg.py`
- `test_extraction_eval.py`

### 10.18 `scripts/evaluate_extraction.py`

作用：评估知识抽取效果，并判断是否需要引入 RAG。

输入：

- `profiles.jsonl`
- 可选 `validation_results.jsonl`

输出：

- `extraction_eval.json`
- `extraction_eval.md`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\evaluate_extraction.py
```

### 10.19 `src/jd_parser/rag.py`

作用：实现本地 RAG 增强。它从已有 Profile 构建技能检索索引，召回候选技能，并用当前 JD 原文证据进行门控。

输入：

- 原始 `profiles.jsonl`

输出：

- RAG 增强后的 Profile；
- 新增技能审计；
- 校验结果；
- RAG summary。

使用方式：

```python
from pathlib import Path
from jd_parser.rag import run_rag_augmentation

summary = run_rag_augmentation(
    Path("data/output/real_9000/profiles.jsonl"),
    Path("data/output/rag_real_9000"),
)
```

### 10.20 `scripts/run_rag_augmentation.py`

作用：一键运行 RAG 增强。

输入：

- `data/output/real_9000/profiles.jsonl`

输出：

- `data/output/rag_real_9000/`

使用：

```powershell
cd D:\vs\job-ability-graph\jd-parser
python scripts\run_rag_augmentation.py
```

## 11. 常见问题

### 11.1 为什么技能节点只有 225 个？

当前阶段没有做技能归一化，只根据 JD Profile 中已经抽取出的技能表面词构图。后续可以增加技能归一化模块，把 `PyTorch`、`pytorch`、`torch框架` 等合并。

### 11.2 为什么有些岗位没有技能边？

有效性报告中的 `jobs_without_skill_edges` 表示部分 JD 在当前规则下没有抽到技能。这通常是因为岗位文本缺少明确技术词，或者抽取规则词表覆盖不足。它是覆盖率问题，不是图结构错误。

### 11.3 图谱是否可以导入 Neo4j？

可以。`graph_nodes.jsonl` 和 `graph_edges.jsonl` 已经是节点/边分离格式。后续可写导入脚本，将：

- `node_id` 映射为 Neo4j 节点唯一键；
- `label` 映射为 Neo4j label；
- `relation_type` 映射为 Neo4j relationship type；
- `properties` 映射为节点或边属性。

### 11.4 网页打开很慢怎么办？

不要直接让网页加载完整的 `graph_edges.jsonl`。当前网页使用 `scripts/build_kg_web.py` 生成的轻量数据包，只加载 Top Skills、技能索引和局部子图，适合浏览器展示。
