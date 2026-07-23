# 岗位原始数据 `jd_raw.jsonl` 生成流程说明报告

## 一、文档目的

本文档用于说明项目中岗位原始数据文件 `data/small-raw/jd_raw.jsonl` 的生成来源、处理流程、相关脚本职责以及后续维护方式。该说明可用于项目汇报、代码交接和数据处理流程解释。

## 二、数据文件概述

`jd_raw.jsonl` 是本项目岗位能力图谱构建流程中的岗位原始数据文件。文件采用 JSON Lines 格式存储，即每一行对应一条岗位记录。

当前数据主要来源于智联招聘搜索页缓存，经过岗位解析、去重、AI 技术岗位筛选、字段规范化后写入。

相关输出文件如下：

| 文件或目录 | 说明 |
|---|---|
| `data/small-raw/jd_raw.jsonl` | 岗位原始数据主文件，每行一条岗位 JSON 记录 |
| `data/small-raw/jd_raw.csv` | 与 `jd_raw.jsonl` 同步生成的 CSV 文件，便于表格查看 |
| `data/small-raw/jd_raw_summary.json` | 数据生成摘要，记录保存条数、过滤规则、统计信息等 |
| `data/small-raw/_jd_ai_fetch_tmp/` | 智联搜索页 HTML 缓存目录，不是最终数据 |
| `*.out.log` | 脚本运行的标准输出日志，通常记录进度和统计信息 |
| `*.err.log` | 脚本运行的错误输出日志，通常记录异常、报错和警告 |

## 三、整体生成流程

`jd_raw.jsonl` 的生成流程可以分为四个阶段：

1. 抓取智联招聘搜索页，并保存为本地 HTML 缓存；
2. 从缓存页面中解析岗位列表；
3. 按照 AI 技术岗位规则进行筛选、去重和字段规范化；
4. 写出 `jd_raw.jsonl`、`jd_raw.csv` 和 `jd_raw_summary.json`。

流程如下：

```text
智联招聘搜索页
        │
        ▼
HTML 缓存文件
data/small-raw/_jd_ai_fetch_tmp/*.html
        │
        ▼
岗位解析与字段转换
scripts/append_ai_jd_data.py
        │
        ▼
AI 技术岗位过滤
scripts/rebuild_strong_ai_jd_data.py
scripts/refill_title_ai_jd_data.py
        │
        ▼
数据写出
scripts/refill_title_ai_jd_data.py:write_outputs(...)
        │
        ├── data/small-raw/jd_raw.jsonl
        ├── data/small-raw/jd_raw.csv
        └── data/small-raw/jd_raw_summary.json
```

## 四、核心脚本职责

| 脚本文件 | 主要职责 | 是否直接影响 `jd_raw.jsonl` |
|---|---|---|
| `scripts/expand_zhaopin_cache.py` | 抓取智联招聘搜索页，并写入本地 HTML 缓存 | 不直接写入 |
| `scripts/refill_from_longtail_zhaopin_cache.py` | 针对新增或长尾关键词缓存进行岗位补全，并调用写出逻辑 | 间接写入 |
| `scripts/refill_title_ai_jd_data.py` | 扫描缓存、筛选岗位、去重，并写出最终数据文件 | 直接写入 |
| `scripts/rebuild_strong_ai_jd_data.py` | 定义强 AI/机器学习相关岗位的过滤规则 | 参与筛选 |
| `scripts/append_ai_jd_data.py` | 解析智联 HTML 页面、转换岗位字段、处理薪资和日期等 | 提供基础工具函数 |
| `scripts/run_profile_preview.py` | 基于已有岗位和简历数据进行画像抽样预览 | 不参与生成 |
| `scripts/build_esco_index.py` | 构建 ESCO 能力词表索引 | 不参与生成 |

其中，真正负责写出 `jd_raw.jsonl` 的核心逻辑位于：

```text
scripts/refill_title_ai_jd_data.py
```

`refill_from_longtail_zhaopin_cache.py` 本身不重复实现写出逻辑，而是复用 `refill_title_ai_jd_data.py` 中的输出函数。

## 五、关键数据处理逻辑

### 1. 岗位解析

岗位解析主要由 `scripts/append_ai_jd_data.py` 完成。该脚本负责从智联搜索页 HTML 中提取岗位信息，并统一转换为项目需要的字段格式。

主要处理内容包括：

- 岗位 ID；
- 岗位名称；
- 公司名称；
- 行业；
- 工作地点；
- 薪资范围；
- 工作经验；
- 学历要求；
- 发布时间；
- 岗位描述文本；
- 技能字段；
- 岗位链接。

### 2. 岗位筛选

岗位筛选主要由以下两个脚本共同完成：

```text
scripts/rebuild_strong_ai_jd_data.py
scripts/refill_title_ai_jd_data.py
```

当前筛选目标是保留与人工智能技术相关的岗位，而不是简单保留所有标题中带有 “AI” 的岗位。

保留方向主要包括：

- AI 开发工程师；
- AI 研发工程师；
- 算法工程师；
- 大模型工程师；
- LLM / RAG / Agent / 智能体开发；
- NLP / CV / 机器视觉 / 图像算法；
- 模型训练、模型推理、模型微调、模型部署；
- AI 平台、MLOps、AI Infra 等技术岗位。

排除方向主要包括：

- 销售、售前、售后；
- 市场、营销、广告投放；
- 运营、内容运营、短视频、直播；
- 美术、动漫、剪辑、文案；
- 普通数据分析师；
- 普通测试、调试、标注兼职；
- 仅使用 AI 工具但不从事 AI 技术开发的岗位。

### 3. 去重规则

当前主要按 `job_id` 去重。即同一个智联岗位 ID 只保留一条记录，避免同一岗位因不同关键词、不同城市搜索结果重复进入数据集。

## 六、`jd_raw_summary.json` 的作用

`jd_raw_summary.json` 是生成结果摘要文件，不是配置文件。

它主要用于记录：

- 数据来源；
- 保存条数；
- 目标条数；
- 过滤规则说明；
- 扫描缓存数量；
- 解析岗位数量；
- 新增岗位数量；
- 去重和过滤统计。

因此，修改 `jd_raw_summary.json` 不会控制 `jd_raw.jsonl` 的生成。真正控制数据生成的是相关 Python 脚本。

## 七、日志文件说明

项目中存在一些 `.log` 文件，例如：

```text
refill_cache_existing_words.out.log
refill_cache_existing_words.err.log
start_test.out.log
start_test.err.log
```

这些文件只是脚本运行记录。

| 日志类型 | 作用 |
|---|---|
| `.out.log` | 记录脚本正常输出，例如运行进度、统计结果 |
| `.err.log` | 记录脚本错误输出，例如异常栈、报错信息、警告 |

日志文件不会控制 `jd_raw.jsonl` 的生成，也不是数据源。若不需要追溯历史运行情况，可以清理；若需要排查脚本执行问题，建议保留。

## 八、后续维护建议

### 1. 如果需要扩展岗位来源

优先修改或运行：

```text
scripts/expand_zhaopin_cache.py
```

该脚本负责扩展智联招聘搜索页缓存。

### 2. 如果需要调整岗位筛选标准

优先修改：

```text
scripts/refill_title_ai_jd_data.py
scripts/rebuild_strong_ai_jd_data.py
```

这两个脚本决定哪些岗位可以进入最终数据集。

### 3. 如果需要重新生成最终数据

可使用缓存补全脚本重新筛选并写出：

```powershell
python scripts\refill_title_ai_jd_data.py --target-total 15000 --max-cache-page 60 --min-cache-bytes 50000 --workers 24 --write-partial
```

也可以只针对新增长尾缓存补全：

```powershell
python scripts\refill_from_longtail_zhaopin_cache.py --target-total 15000 --max-cache-page 3 --min-cache-bytes 1 --workers 32 --write-partial
```

## 九、总结

`jd_raw.jsonl` 是项目岗位能力图谱构建中的基础数据文件。它的生成不是单个文件独立完成的，而是由“智联缓存抓取、岗位解析、AI 技术岗位过滤、数据写出”组成的一条数据处理链路。

其中：

- `expand_zhaopin_cache.py` 负责扩展智联缓存；
- `append_ai_jd_data.py` 负责岗位解析和字段转换；
- `rebuild_strong_ai_jd_data.py` 和 `refill_title_ai_jd_data.py` 负责岗位过滤；
- `refill_title_ai_jd_data.py` 最终写出 `jd_raw.jsonl`；
- `refill_from_longtail_zhaopin_cache.py` 用于针对新增缓存进行定向补全。

因此，若后续需要解释数据来源或修改数据生成逻辑，应优先关注上述脚本，而不是直接修改 `jd_raw.jsonl` 或 `jd_raw_summary.json`。

