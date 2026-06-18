# JD 数据采集清单

## 目标

- 先采 100 条岗位 JD：5 个招聘平台各 20 条
- 再补 20-50 条企业官网 JD 做高质量验证
- 最后用 O*NET / ESCO / 职业标准系统统一技能名称
- 不采真实个人简历；简历测试用公开数据、匿名化样例或自造样例

## 1. 招聘平台

建议优先从公开职位详情页采样，覆盖不同技术栈和岗位级别。

| 平台 | 网址 | 适合抓什么 |
| --- | --- | --- |
| 前程无忧 | https://www.51job.com/ | 传统招聘 JD、岗位要求、经验学历 |
| BOSS直聘 | https://www.zhipin.com/ | 新岗位、技能词更口语化 |
| 智联招聘 | https://www.zhaopin.com/ | 覆盖面广，适合做横向对比 |
| 猎聘 | https://www.liepin.com/ | 中高阶岗位、能力要求更细 |
| 拉勾 | https://www.lagou.com/ | 互联网/技术岗密度高 |

## 2. 企业官网

优先抓：

- 腾讯招聘：https://join.qq.com/
- 阿里招聘：https://talent.alibaba.com/
- 华为招聘：https://career.huawei.com/
- 字节招聘：https://jobs.bytedance.com/
- 百度招聘：https://talent.baidu.com/

## 3. 统一技能词表

- O*NET：https://www.onetcenter.org/database.html
- ESCO：https://esco.ec.europa.eu/en/use-esco/download
- 国内职业标准：https://www.osta.org.cn/

## 4. 建议落库字段

```text
source_type
source_name
job_title
company_name
industry
location
salary_min
salary_max
experience
education
publish_date
jd_text
responsibilities
requirements
skills_raw
skills_norm
url
scrape_time
```

## 5. 简历测试集

不要爬真实简历。建议使用公开数据集、匿名化样例或自造样例。
