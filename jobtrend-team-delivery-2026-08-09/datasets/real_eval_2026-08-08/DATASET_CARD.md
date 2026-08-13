# INTERNAL-ONLY — 真实 JD 评测数据卡

禁止公开发布、上传公开网盘、提交到 Git 或转发给团队外人员。本目录包含来自企业官网、标记为
`source-reference-only` 的完整岗位正文，只供本项目组内部评测与标注使用。

## 数据概况

- 数据集目录：`real_eval_2026-08-08`
- 采集日期：`2026-08-08`
- 快照周：`2026-W32`
- 完整 JD：140 条
- 企业数：5 家
- 联系方式检查：未发现邮箱或电话号码
- 时间有效性：只有一个真实采集周，只可做横截面抽取/去重/RAG 评测，不能声称趋势精度

| 来源 | JD 数 |
|---|---:|
| baidu | 32 |
| huawei | 12 |
| meituan | 32 |
| tencent | 32 |
| xiaomi | 32 |

## 首周真实流水线结果

本包保存了固定白名单内的公开分析输出：140 个岗位观测、
110 条趋势特征、0 个新岗位候选、
0 个岗位能力更新和 0 条图谱增量。
`quality_report.json` 为 `valid`。0 个新岗位候选是首周持续性门槛的正确结果，不能据此计算或
声称趋势精度。


## 目录

- `private/jobs.full.jsonl`：140 条完整 JD 汇总。
- `private/jobs/*.jsonl`：按官网来源拆分的完整 JD；与汇总文件可精确重建。
- `sources.yaml`：已经重定位，可直接交给 `jobtrend ingest`。
- `annotations/`：A/B 独立标注、仲裁和评测模板；可能为空，也可能包含内部金标。
- `shareable/`：不含 JD 正文的 URL、哈希及采集审计索引。
- `pipeline_outputs/`：首周真实运行的固定白名单输出；不含 warehouse、DuckDB 或 Qdrant。
- `collection_report.json`：采集数量、来源与权利边界。

## 明确排除

本包不含 `private/raw/` HTTP 原始响应，不含政策、标准或行业报告的 PDF/HTML/DOCX/TXT
全文，不含简历、候选人姓名、邮箱或电话号码，也不含 API key。
