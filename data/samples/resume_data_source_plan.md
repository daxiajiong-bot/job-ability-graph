# 简历数据获取与构造说明

本文件说明 esume_raw.jsonl / esume_raw.csv 的来源方法。为避免个人隐私风险，本项目不爬取真实个人简历。

## 输出文件

- data/outputs/resume_raw.jsonl：结构化简历数据，保留数组字段。
- data/outputs/resume_raw.csv：Excel 友好的简历数据。
- data/outputs/resume_raw_summary.json：数量、来源方法、匹配等级统计。
- data/samples/resume_samples.json：前 12 条样例。

## 与 JD 的对应方式

每条简历都包含：

- 	arget_job_id
- 	arget_job_title
- 	arget_company_name
- 	arget_skills_norm
- match_level
- expected_match_score

当前生成 100 条简历，对应 data/outputs/jd_raw.csv 中 100 条 JD。

## 三种获取方法

1. 公开匿名数据集风格参考：参考 JobHop、CareerBERT 等公开研究中的匿名职业轨迹/技能匹配字段设计，不复制真实个人简历。
2. 人工匿名化样例：按技术简历常见结构手工构造，不包含姓名、电话、邮箱、学校等身份信息。
3. JD 反向合成：根据目标 JD 的岗位名称、学历、经验、技能字段生成可用于 MVP 验证的合成简历。

## 合规说明

真实个人简历属于高敏感个人信息，不建议直接抓取。项目阶段建议只使用公开匿名数据集、匿名样例或合成测试简历。

## 参考来源

- JobHop: https://arxiv.org/abs/2505.07653
- Career Path Prediction / CareerBERT: https://arxiv.org/abs/2310.15636
- ESCO ESCOpedia: https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia