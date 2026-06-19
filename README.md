# job-ability-graph

岗位能力图谱与人岗匹配最小可运行脚手架。

## 现在能做什么

- 抓取公开 JD 搜索页
- 解析岗位基础字段和技能词
- 统一技能名称
- 导出 JSONL/JSON

## 数据源

- 智联招聘
- 拉勾招聘
- 企业官网公开岗位页

## 运行

```bash
pip install -r requirements.txt
python -m backend.main collect --keyword Python --target-count 100 --output data/outputs/jd_raw.jsonl
```

## 说明

- 默认只抓公开页面
- 不采真实个人简历
- 简历测试建议用公开数据集、匿名化样例或自造样例
