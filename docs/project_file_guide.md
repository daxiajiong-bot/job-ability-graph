# 项目文件总览与使用顺序

这份文档把仓库里的主要文件、目录、输入、输出和推荐使用顺序串起来。  
重点是两条线：

1. `backend/`：抓取原始 JD。
2. `jd-parser/`：清洗、抽取、校验、序列化、建图、评估、可视化。

## 1. 推荐使用顺序

### 1.1 只看核心流水线

```text
原始 JD 来源
-> backend/main.py 或现成 data/input/*.jsonl
-> jd-parser/src/jd_parser/batch.py
-> jd-parser/src/jd_parser/validator.py
-> jd-parser/src/jd_parser/serializer.py
-> jd-parser/src/jd_parser/kg.py
-> jd-parser/scripts/build_kg_web.py
```

### 1.2 如果要跑完整项目

```text
1. 安装依赖
2. 采集或准备输入数据
3. 批量抽取 JD Profile
4. 生成人工复核报告
5. 构建知识图谱
6. 构建网页可视化
7. 评估抽取质量
8. 可选：RAG 增强
9. 可选：用增强后的 Profile 重新建图
```

### 1.3 一条最常见的实际路径

```powershell
cd jd-parser
python scripts\prepare_real_jd.py
python -m jd_parser.cli batch ...
python -m jd_parser.cli kg ...
python scripts\build_kg_web.py
python scripts\evaluate_extraction.py
python scripts\run_rag_augmentation.py
```

## 2. 根目录文件

| 文件 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| `README.md` | 仓库总说明，介绍项目目标和最基础的运行方式 | 无 | 无 |
| `requirements.txt` | 根环境依赖列表 | 无 | 无 |
| `.vscode/launch.json` | VS Code 调试配置，方便直接调试测试文件和当前 Python 文件 | 无 | VS Code 调试入口 |

## 3. `backend/` 文件

这部分负责“采集原始 JD”。

| 文件 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| `backend/main.py` | 后端命令行入口，支持 `collect` 和 `export` | `keyword`、`target_count`、`output` | `data/outputs/jd_raw.jsonl` 或指定 JSONL |
| `backend/config.py` | 配置中心，放站点配置、技能同义词、默认关键词 | 无 | 常量对象 |
| `backend/scrapers.py` | 请求网页并调用解析器，返回标准化 `JDRecord` | 搜索页 URL、关键词、站点配置 | `list[JDRecord]` |
| `backend/parsers.py` | 解析招聘网站 HTML，提取职位、公司、地点、文本、技能 | HTML 文本 | `JDRecord` 或 `list[JDRecord]` |
| `backend/schemas.py` | 后端阶段的数据模型定义 | Python dict / JSON | `JDRecord`、`ResumeRecord`、`MatchResult` |
| `backend/skill_normalizer.py` | 技能归一化和候选词抽取 | 文本或技能列表 | 归一化后的技能列表 |

### `backend/` 的使用顺序

```text
config.py
-> parsers.py
-> scrapers.py
-> main.py
```

### `backend/` 的输入输出说明

- 输入：招聘网站搜索页 HTML，或公开页面 HTML。
- 输出：`JDRecord`，最终写成 `data/outputs/jd_raw.jsonl`、`jd_raw.csv`、`jd_raw_summary.json` 这一类原始数据文件。

## 4. `jd-parser/src/jd_parser/` 文件

这部分负责“结构化抽取到图谱构建”。

| 文件 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| `__init__.py` | 包标记，声明模块导出 | 无 | 无 |
| `cleaner.py` | 清洗原始 JD 文本，去掉导航噪声、重复空行、重复段落 | `raw_text: str` | `cleaned_text: str` |
| `extractor.py` | 规则抽取器，切分职责/要求/优先项，并提取技能和约束 | `document_id`、`raw_text` | `JDProfile` |
| `schemas.py` | JD 阶段的主数据模型 | dict / JSON / `JDProfile` | `Skill`、`JDProfile`、`ValidationResult` 等 |
| `validator.py` | 校验 `JDProfile` 是否合规，检查证据、字段、重复技能等 | `JDProfile` 或 dict，外加原文 | `ValidationResult` |
| `serializer.py` | 将 `JDProfile` 序列化为固定模板文本，便于人工查看 | `JDProfile` | `serialized_text: str` |
| `batch.py` | 批处理整条 JSONL 流水线：清洗、抽取、校验、序列化、落盘 | 输入 JSONL | 一组批处理产物 |
| `cli.py` | 命令行入口，提供 `batch` 和 `kg` 子命令 | 命令行参数 | 控制台输出 + 文件产物 |
| `kg.py` | 从 `profiles.jsonl` 构建知识图谱并做有效性检查 | `profiles.jsonl` | 图谱文件、统计文件、验证报告 |
| `rag.py` | 本地 RAG 增强：从已有 Profile 中检索候选技能，再做证据门控 | `profiles.jsonl` | 增强后的 Profile、审计结果、统计文件 |
| `extraction_eval.py` | 评估抽取质量，输出覆盖率、证据支持率、RAG 建议 | `profiles.jsonl`、`validation_results.jsonl` | 评估报告 JSON/Markdown |

### `jd-parser/src/jd_parser/` 的使用顺序

```text
cleaner.py
-> extractor.py
-> validator.py
-> serializer.py
-> batch.py
-> kg.py
-> extraction_eval.py
-> rag.py
```

### 关键模型说明

- `Skill`：技能名、等级、证据。
- `JDConstraints`：学历、经验、地点。
- `JDProfile`：一条 JD 的结构化结果。
- `ValidationResult`：校验后的状态和错误列表。
- `BatchSummary`：批处理统计。

## 5. `jd-parser/scripts/` 文件

这些是更偏“任务级”的封装脚本，通常是把默认路径和常用参数写死，方便一键运行。

| 文件 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| `prepare_real_jd.py` | 从压缩包中取出真实 JD，剔除已采样 ID，生成批处理输入 | JD zip、排除 ID 列表 | `jd_remaining_9000.jsonl`、原始副本、summary |
| `run_sample.py` | 跑 12 条样本，顺便生成人工复核报告 | `data/input/sample_12.jsonl` | `data/output/sample_12/`、`sample_12_review.md` |
| `build_kg.py` | `kg` 命令的默认路径封装 | `real_9000/profiles.jsonl` | `kg_real_9000/` |
| `build_kg_web.py` | 把图谱结果和样本子图拼成网页可视化资源 | KG 输出 + `profiles.jsonl` | `web/index.html`、`assets/graph-data.js` 等 |
| `evaluate_extraction.py` | 抽取评估任务封装 | `profiles.jsonl`、`validation_results.jsonl` | `extraction_eval.json`、`extraction_eval.md` |
| `run_rag_augmentation.py` | 一键跑本地 RAG 增强 | `profiles.jsonl` | `rag_real_9000/` |
| `build_review_report.py` | 生成人工复核 Markdown 报告 | 输入 JSONL + 批处理输出目录 | review Markdown |

### `scripts/` 的推荐顺序

```text
prepare_real_jd.py
-> batch.py / cli.py batch
-> build_review_report.py 或 run_sample.py
-> kg.py / cli.py kg
-> build_kg_web.py
-> evaluate_extraction.py
-> run_rag_augmentation.py
-> 再次 kg.py / build_kg_web.py
```

## 6. `jd-parser/web/` 文件

这是知识图谱网页可视化模板。

| 文件 | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| `web/index.html` | 网页入口，加载图谱数据和脚本 | `assets/graph-data.js`、`assets/app.js`、`assets/styles.css` | 浏览器页面 |
| `web/assets/app.js` | 前端交互、SVG 绘图、节点详情、技能切换 | `window.KG_WEB_DATA` | 页面上的交互式图谱 |
| `web/assets/styles.css` | 页面样式 | HTML 结构 | 可视化样式 |

### `web/` 的使用顺序

```text
build_kg_web.py
-> graph-data.js
-> index.html
-> app.js
-> styles.css
```

## 7. `jd-parser/docs/` 文件

| 文件 | 作用 | 备注 |
| --- | --- | --- |
| `docs/kg_usage.md` | 讲解如何使用 9000 条 JD 的知识图谱结果 | 偏使用说明 |
| `docs/kg_build_flow.md` | 讲解建图流程图和核心数据流 | 偏流程说明 |

## 8. `jd-parser/tests/` 文件

这些文件是单元测试，用来确认清洗、抽取、校验、序列化、图谱、评估逻辑都正常。

| 文件 | 作用 |
| --- | --- |
| `test_cleaner.py` | 测试清洗规则 |
| `test_extractor.py` | 测试规则抽取器 |
| `test_validator.py` | 测试校验逻辑 |
| `test_serializer.py` | 测试序列化模板 |
| `test_kg.py` | 测试知识图谱构建 |
| `test_extraction_eval.py` | 测试评估报告 |
| `test_rag.py` | 测试本地 RAG 增强 |

## 9. `data/` 目录说明

### 9.1 输入类

| 文件或目录 | 作用 | 输入格式 |
| --- | --- | --- |
| `data/input/sample_12.jsonl` | 12 条样本输入 | 每行一个 `{document_id, raw_text}` |
| `data/input/jd_remaining_9000.jsonl` | 真实 JD 批处理输入 | 每行一个标准输入记录 |
| `data/samples/jd_samples.json` | JD 示例样本 | JSON 示例 |
| `data/samples/resume_samples.json` | 简历示例样本 | JSON 示例 |
| `data/samples/*.md` | 数据来源和规划说明 | Markdown |

### 9.2 批处理输出类

| 文件 | 作用 |
| --- | --- |
| `profiles.jsonl` | 抽取后的 `JDProfile` |
| `validation_results.jsonl` | 每条记录的校验结果 |
| `serialized.jsonl` | 序列化后的可读文本 |
| `cleaned.jsonl` | 清洗后的文本 |
| `raw_model_outputs.jsonl` | 抽取器原始输出 |
| `errors.jsonl` | 失败记录 |
| `summary.json` | 批处理统计 |

### 9.3 图谱输出类

| 文件 | 作用 |
| --- | --- |
| `graph_nodes.jsonl` | 图谱节点 |
| `graph_edges.jsonl` | 图谱边 |
| `graph_summary.json` | 节点数、边数、覆盖率、Top 技能 |
| `validation_report.json` | 图谱有效性检查结果 |
| `top_skills.csv` | 技能频次统计 |
| `sample_subgraph_first_5.json` | 前 5 个岗位的局部子图 |
| `sample_subgraph_first_5.md` | 子图 Markdown 预览 |
| `sample_subgraph_first_5.html` | 子图 HTML 预览 |
| `web/` | 网页可视化产物 |

### 9.4 RAG 输出类

| 文件 | 作用 |
| --- | --- |
| `rag_added_skills.jsonl` | 每条 JD 新增了哪些技能 |
| `retrieval_index_summary.json` | 本地检索索引摘要 |
| `summary.json` | 增强统计 |

### 9.5 历史数据目录

以下目录保存的是不同阶段的样本或输出，结构和上面的规则一致：

- `data/outputs/`
- `data/jd-raw-3000/`
- `data/resume_synthetic_lstk_tech_v1/`
- `data/small_raw_200_lskt_tech_v2/`
- `jd-parser/data/input/`
- `jd-parser/data/output/`

它们本质上都是“同一套 schema 的不同批次结果”。

## 10. 一句话理解每个阶段

- `backend`：把网页变成原始 JD JSONL。
- `cleaner`：把文本里的噪声去掉。
- `extractor`：把文本变成结构化 Profile。
- `validator`：检查这个 Profile 是否可信。
- `serializer`：把 Profile 再变成人能读的固定模板。
- `batch`：把一堆 JD 全部串起来跑。
- `kg`：把 Profile 变成图谱。
- `rag`：在不引入外部幻觉的前提下补技能。
- `extraction_eval`：看当前抽取到底稳不稳。
- `build_kg_web`：把图谱结果做成网页。

## 11. 最小运行顺序速查

### 11.1 只跑单元测试

```powershell
cd jd-parser
python -m unittest discover -s tests
```

### 11.2 跑批处理

```powershell
cd jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli batch --input data\input\jd_remaining_9000.jsonl --output data\output\real_9000
```

### 11.3 构图

```powershell
cd jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli kg --profiles data\output\real_9000\profiles.jsonl --output data\output\kg_real_9000
```

### 11.4 生成网页

```powershell
cd jd-parser
python scripts\build_kg_web.py
```

### 11.5 评估与增强

```powershell
cd jd-parser
python scripts\evaluate_extraction.py
python scripts\run_rag_augmentation.py
```

如果你只记一条：**先批处理，再建图，再出网页，最后再做评估和 RAG。**

