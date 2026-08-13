# 数据源治理

## 源清单

- `data/samples/sources.yaml`：120 条合成 JD 和 2 份合成支持文档，可再分发，用于离线演示和 CI。
- `data/real_eval/snapshots/2026-08-08/`：首个真实官网评测快照，5 家企业共 140 条 JD；完整正文位于忽略的 `private/`，可交付部分只有无正文参考索引，标注模板及金标也默认不随公开交接包分发。
- `sources/authoritative_sources.yaml`：恰好 10 个政策/职业标准与 10 个正式权威行业报告条目。它只保留发布方 URL；不使用 `ictp.caict.ac.cn` 的期刊摘要页作为报告来源。数字中国发展报告归入 `industry_report`，不计入政策配额。默认 `enabled: false`，必须在确认访问频率、使用条款和网络环境后逐条启用。

每条清单均为严格的 `source_manifest_v1` `SourceSpec`：`source_id` 全局唯一，`source_type`、`input_format` 和 `enabled` 受 schema 校验；`published_at` 仅在发布日已核实时填写，无法确认时有意留空。`metadata.rights` 采用保守的统一声明：`redistribution_allowed: false`、`fulltext_in_handoff: false`、`allowed_output: metadata_hash_and_necessary_evidence_excerpt_only`、`terms_review_required: true`。该声明是交付控制，不替代每个网站的实际许可条款复核。

## 每周快照

对每个企业官网数据源保存完整快照，而不是只保存与上周的差异。推荐文件名：

```text
input/jobs/<source_name>/YYYY-Www.jsonl
```

每条 JD 至少包含：`job_id`、`job_title`、`company_name`、`jd_text`、`publish_date`、`scrape_time`、`url`。若缺少发布时间，保留空值，不得用采集时间冒充。

新岗位的“连续周”按 `scrape_time` / `collected_at` 所在采集周计算，不按 `publish_date` 计算。可选 `snapshot_week`（如 `2026-W32`）或包含 ISO 日期的 `snapshot_id` 仅作审计标签：系统会核验它是否与 `collected_at` 同周，不一致或无法解析时一律使用 `collected_at` 所在周。

## 许可与再分发

- 交付包可包含明确授权、公共领域或合成数据。
- 对 `source-reference-only` 条目，交付包仅保存 URL、元数据、源文件哈希与为审核所必需的短证据片段，不打包完整原文；导出器会拒绝非空全文，并将片段硬限制为最多 3 段、每段 300 字符且必须带页码/章节/字符区间。任何再分发、全文缓存或批量下载仍须先取得相应授权。
- 不存储简历、电话、邮箱、候选人姓名等个人信息。
- URL 获取失败时保留失败元数据，不将网站错误页当作正文。
- `private/` 和真实评测 `annotations/` 不仅由 Git 忽略，也由 Docker 构建上下文和交接包导出器强制排除；不能只依赖开发者本机的 ignore 规则。

### 组内数据交接

`scripts/build_team_delivery.py` 是与公共导出器分开的显式边界。它只接受固定白名单，生成标为 `INTERNAL-ONLY` 的外层归档：可以包含 140 条官网 JD 全文、标注模板、首周真实分析输出，以及经过联系方式过滤的 10,510 条智联历史 JD。外层包仍禁止包含原始 HTTP 响应、政策/标准/报告全文、简历、联系方式、密钥、模型权重、数据库与向量缓存。

这类完整包只能发给本项目组成员，不能上传公开 Git、公开网盘或作为比赛公开附件。需要公开演示或发给团队外人员时，只使用标准组件导出，其真实数据部分仅保留 URL、哈希、时间和必要审计元数据。

## 质量注意

现有约 10,515 条 JD 可作为初始语料，但来源单一，且旧 `publish_date` 不等于真实历史快照。报告时必须分开标注“历史导入”与“持续观测”，单一来源候选不得标为高置信度。

2026-08-08 已接通 5 家企业官网并完成首周 140 条快照。它可用于字段抽取、去重和横截面检索评测，但不足以验证时序趋势；至少 2 个真实采集周才能检查持续性门槛，完整 112 天窗口需要至少 16 周。
