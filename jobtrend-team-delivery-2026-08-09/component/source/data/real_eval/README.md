# 真实评测数据

本目录保存公开企业招聘官网的周快照和评测标注模板。完整 JD 与原始 HTTP 响应仅用于队内学术评测，统一放在每个快照的 `private/` 下；该目录被 Git、Docker 构建上下文和交接包导出器共同排除。

## 已完成快照

`snapshots/2026-08-08/` 是首个真实快照：

- 腾讯、美团、小米、百度各 32 条，华为 12 条，共 140 条完整 JD、5 家企业。
- 140 条均含职责和要求；76 条有官网明确发布时间，其余保持空值。
- 140 个来源内岗位 ID 唯一，124 个正文哈希唯一；重复版本保留用于去重评测。
- 20 条校准集、120 条盲测集；同公司精确/高相似版本不会跨集合。
- 400 对去重标注样本，以及每位标注员 60 个 RAG 查询模板。

`shareable/` 只有 URL、标题、公司、时间、哈希、请求审计和结构校验结果，不含职责、要求或完整正文。`annotations/` 当前是未填写模板；它与 `private/` 一样不会自动进入 Git、Docker 或交接包，不能把空模板计算成真实精度。

## 复现一次周采集

先人工复核目标官网的使用条款和 robots 状态，再执行：

```bash
.venv/bin/python scripts/collect_public_eval.py \
  --output-root data/real_eval/snapshots \
  --keyword 大模型
```

采集器仅访问内置的企业招聘官网 allow-list，按域名串行限速，遇到 401、403、429 立即停止；不登录、不投递、不访问 referral/apply 页面，也不采集简历或联系方式。同一天的已完成快照拒绝覆盖。

完整 JD 进入流水线：

```bash
.venv/bin/jobtrend ingest \
  --sources data/real_eval/snapshots/2026-08-08/private/sources.yaml \
  --warehouse runs/real-eval-2026-08-08/warehouse

.venv/bin/jobtrend analyze \
  --warehouse runs/real-eval-2026-08-08/warehouse \
  --output runs/real-eval-2026-08-08/analysis \
  --as-of 2026-08-09T00:00:00+08:00

.venv/bin/python scripts/validate_real_eval.py \
  data/real_eval/snapshots/2026-08-08 \
  --warehouse runs/real-eval-2026-08-08/warehouse \
  --analysis runs/real-eval-2026-08-08/analysis
```

首次真实运行得到 140 个文档、144 条证据、140 个岗位观测和 110 条趋势特征，结构校验为 `structural_pass`。只有一个真实采集周，因此新岗位和技能变化结果为空是预期行为；不得用历史 `publish_date` 伪造连续周趋势。

## 完成金标

1. 标注员 A、B 分别填写 `jd_annotations_A/B.jsonl`、`dedup_pairs_A/B.csv` 和 `rag_queries_A/B.jsonl`，彼此不可查看答案。
2. 先只使用 20 条 calibration 调整规则；冻结后不得根据 120 条 test 修改 Prompt、别名或阈值。
3. 仲裁结果写入单独的 `*_adjudicated` 文件，保留 A/B 原始记录。
4. 只有双人标注和仲裁完成后，才能填写 P/R/F1、近重 Precision 和 RAG Recall@20；当前所有金标指标均为 `null`。
5. 已填写的标注可能含必要原文片段和盲测答案，默认只在 `annotations/` 本地保存；如确需另行交付，必须按 `source-reference-only` 权利规则单独审查。

完整评测记录见 `docs/real_evaluation.md` 和 `docs/annotation_guide.md`。
