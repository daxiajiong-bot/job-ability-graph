# 数据流说明

## 输入来源

当前 demo 支持三类输入：

- 纯文本 JD；
- 纯文本简历；
- 通过 `input_adapters/document_text.py` 转成文本的简历文档。

样例数据位于：

- `data/samples/jd_samples.json`
- `data/samples/resume_samples.json`

用户补充爬取的 100 条 JD 和简历原始数据可以继续保存在：

- `data/raw/jd/`
- `data/raw/resume/`

## 处理流程

```text
原始文本
  -> 章节/字段解析
  -> 技能证据抽取
  -> 技能归一化
  -> 岗位画像 / 候选人画像
  -> 人岗匹配评分
  -> 能力差距分析
  -> 完整图谱构建
  -> 视图图谱抽取
  -> JSON 分层落盘
```

## 分层产物

| 层级 | 目录 | 说明 |
| --- | --- | --- |
| raw | `data/raw/jd`、`data/raw/resume` | 原始文本和来源元数据 |
| parsed | `data/parsed/jd_profiles`、`data/parsed/resume_profiles` | 结构化岗位/候选人画像 |
| normalized | `data/normalized` | 归一化后的技能、能力域、技术栈、等级信息 |
| evidence | `data/evidence/evidence_index.json` | 技能和画像字段对应的证据片段 |
| matches | `data/matches` | 匹配分数、决策、差距详情、LLM 状态 |
| graph | `data/graph` | 完整图谱和岗位/技术栈/等级/匹配/演化视图 |
| evaluation | `data/evaluation/evaluation_result.json` | 样例评测结果 |

## 稳定 ID

`backend/app/storage/id_generator.py` 负责生成稳定 ID。中文文本会保留可读前缀并附加 hash 后缀，因此重复运行会覆盖同一类确定性产物，不会生成随机文件名。
