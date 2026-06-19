# 评测说明

## 运行方式

```bash
python3 scripts/evaluate_samples.py
```

脚本会读取：

- `data/samples/jd_samples.json`
- `data/samples/resume_samples.json`

评测逻辑：

1. 遍历每条样例 JD；
2. 将该 JD 与全部样例简历逐一匹配；
3. 按 `final_score` 从高到低排序；
4. 判断 Top-1 简历是否落在 JD 的 `expected_match_resumes` 中；
5. 输出 Top-3 排名和整体 `top1_accuracy`；
6. 写入 `data/evaluation/evaluation_result.json`。

## 输出字段

- `generated_at`：评测生成时间；
- `metric`：当前主指标，默认为 `top1_accuracy`；
- `top1_accuracy`：样例 JD 的 Top-1 命中率；
- `jd_count`：参与评测的 JD 数量；
- `resume_count`：参与评测的简历数量；
- `details[].top3`：每条 JD 的 Top-3 候选人；
- `details[].top1_hit`：该 JD 的 Top-1 是否命中预期；
- `top3[].final_score`：匹配分数；
- `top3[].decision`：推荐/可考虑/不推荐等决策。

## 比赛 demo 解读

这个评测不是生产级招聘效果 benchmark，而是 demo 的可重复验收脚本。现场可以用它证明：

- 规则解析、匹配和图谱构建链路能批量跑通；
- 匹配结果具有可解释字段；
- 评测结果会落盘，便于复现和展示；
- 后续可以扩展为 Precision@K、Recall@K、MRR、人工标注集评测等指标。
