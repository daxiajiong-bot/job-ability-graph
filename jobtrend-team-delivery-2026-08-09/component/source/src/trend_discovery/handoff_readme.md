# JobTrend 趋势与新岗位发现组件

请先读本文件。这个目录是可独立安装、离线演示并通过 JSONL/CSV 与其他组员交接的组件包。

## 这个包做什么

- 输入招聘 JD，以及政策、职业标准、行业报告的 PDF、HTML、DOCX、TXT 或公开 URL。
- 输出趋势特征、新岗位候选、已有岗位技能变化、证据定位、人工审核表和只追加知识图谱增量。
- 只读导入队友的 `jd_kg_v1` 或 `small-raw-lskt-tech/v2` 图谱，不修改原图，不重新生成原节点 ID。

它不包含 REST API、前端、简历解析、人岗匹配或实时通用爬虫。

## 目录先看这里

```text
README.md                      当前说明
dist/*.whl                     可安装 wheel
source/                        完整源码、配置、测试和详细文档
schemas/                       公开 JSON Schema
external_documents.jsonl       本次缓存输出的统一文档
evidence.jsonl                 可定位证据
trend_features.jsonl           趋势指标
emerging_roles.jsonl           新岗位候选
job_skill_updates.jsonl        已有岗位技能变化
review_queue.csv               人工审核入口
kg_link_delta.jsonl            append-only 图谱增量
manifest.json                  哈希、数量、模型、Prompt、费用和图指纹
LOCAL_VALIDATION.json          构建机自测记录
```

本包根目录的缓存输出类型：**{{DATASET_LABEL}}**。

缓存记录数：统一文档 {{DOCUMENT_COUNT}}、证据 {{EVIDENCE_COUNT}}、趋势特征 {{TREND_COUNT}}、新岗位候选 {{ROLE_COUNT}}、技能更新 {{UPDATE_COUNT}}、图谱增量 {{DELTA_COUNT}}。

## 3 分钟安装和离线演示

要求 Python 3.11 或更高版本。首次安装依赖通常需要访问 Python 包索引；安装完成后的示例运行不访问招聘网站、不调用云模型、不产生模型费用。

在本 README 所在目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r source/requirements.lock
python -m pip install --no-deps dist/trend_discovery_service-*.whl

jobtrend --help
jobtrend --pretty --config source/config/default.yaml run-all \
  --sources source/data/samples/sources.yaml \
  --warehouse work/demo-warehouse \
  --output work/demo-output
```

成功时应至少得到 120 个岗位观测、1 个“AI Agent 安全评测工程师”候选和 1 个“Java 开发工程师”技能更新。`work/` 是新建运行目录，不会覆盖包内缓存输出。

## 接入你们自己的 JD

复制 `source/data/samples/sources.yaml` 后修改。最小清单示例：

```yaml
schema_version: source_manifest_v1
sources:
  - source_id: company-a-2026-W33
    source_type: job
    input: jobs/company-a-2026-W33.jsonl
    input_format: jsonl
    source_name: company-a-careers
    publisher: 示例企业
    collected_at: 2026-08-10T09:00:00+08:00
    license: team-internal
    metadata:
      snapshot_id: 2026-08-10:company-a-careers
      snapshot_week: 2026-W33
```

JD 建议字段为 `job_id`、`job_title`、`company_name`、`jd_text`、`publish_date`、`scrape_time`、`url`。`publish_date` 缺失时保持空值，不能拿采集时间冒充发布时间。新岗位连续周只按真实 `collected_at` 计算。

```bash
jobtrend --pretty --config source/config/default.yaml ingest \
  --sources input/sources.yaml \
  --warehouse work/warehouse

jobtrend --pretty --config source/config/default.yaml analyze \
  --warehouse work/warehouse \
  --output work/analysis
```

## 接入队友知识图谱

```bash
jobtrend --pretty import-kg \
  --nodes /path/to/graph_nodes.jsonl \
  --edges /path/to/graph_edges.jsonl \
  --profiles /path/to/profiles.jsonl \
  --output work/kg-index

jobtrend --pretty --config source/config/default.yaml analyze \
  --warehouse work/warehouse \
  --kg-index work/kg-index \
  --output work/analysis-with-kg
```

`profiles.jsonl` 可省略。导入过程只读并记录图谱指纹；最终只把待审核关系写到 `kg_link_delta.jsonl`，由图谱负责人审核合并。

## 人工审核和交给下一位组员

```bash
jobtrend review-export --run-dir work/analysis

# 填写 review_queue.csv 中的 decision / reviewer / reviewed_at / edits_json
jobtrend review-import \
  --review work/analysis/review_queue.csv \
  --run-dir work/analysis \
  --output work/analysis-reviewed
```

审核导入始终写新目录，不覆盖算法原结果。

## 云模型是可选项

- 不配置 `DASHSCOPE_API_KEY` 仍可完成解析、去重、统计、图谱导入、审核和离线缓存演示。
- `prepare` 只生成本地 Batch 请求，默认不提交、不收费。
- 只有 `submit --execute --confirm SUBMIT_JOBTREND_PAID_BATCH` 才会付费提交。
- `--cloud-retrieval` 会调用云 embedding/rerank；不需要时不要添加。

## 数据与许可边界

- 源码采用 MIT License；标准组员交接包可在 `source/LICENSE` 查看许可证。
- `source/data/samples/` 是可再分发合成数据。
- `source/data/real_eval/.../shareable/` 只有真实来源的 URL、标题、时间、哈希和结构校验，不含完整正文。
- 完整官网 JD、原始响应、政策/报告全文及已填金标不属于公开组件包。若你收到外层 `datasets/real_eval_*`，它是单独标注的 **INTERNAL-ONLY 队内评测数据**，不得上传公开仓库或对外转发。
- `source-reference-only` 文档全文会被导出器拒绝；必要证据最多 3 段、每段 300 字符且必须有定位。

## 常见问题

**为什么真实数据没有新岗位候选？**

至少需要两个真实采集周才能通过持续性门槛；完整 28 天近期窗口加 84 天基线需要 16 周。历史发布时间不能替代周快照。

**为什么 PDF 没进入评分？**

扫描 PDF 文本层不足时会标记 `needs_ocr`。首版不自动 OCR，也不把错误页当正文。

**命令提示参数不存在？**

`--config` 和 `--pretty` 是全局参数，放在子命令之前，例如 `jobtrend --pretty --config ... run-all ...`。

**能否直接修改队友图谱？**

不能。本组件只输出 append-only `kg_link_delta.jsonl`，禁止直接写入对方图谱目录。

## 验证与进一步阅读

```bash
python source/scripts/validate_handoff.py /path/to/jobtrend-component.tar.gz
python -m pip install 'pytest>=8,<10'
python -m pytest -q source/tests
```

- 详细工程说明：`source/README.md`
- 架构边界：`source/docs/architecture.md`
- 数据治理：`source/docs/data_sources.md`
- 真实评测记录：`source/docs/real_evaluation.md`
- 验收状态：`source/docs/acceptance_status.md`
- 测试报告：`source/docs/test_report.md`
