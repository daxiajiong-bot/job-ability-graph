# 团队分工与文件归类

## 王贤炯

职责：

- 技术路线统筹
- JobFormer 论文复现
- Prompt、Skill 编写
- 新岗位发现算法、岗位能力动态更新

## 喻昕之

职责：

- 爬数据：JD、简历
- 根据爬出来的数据生成技能词表
- 知识图谱可视化、更新逻辑

对应内容：

- `data/samples/jd_data_source_plan.md`
- `backend/config.py`
- `backend/scrapers.py`
- `backend/parsers.py`
- `backend/schemas.py`
- `backend/skill_normalizer.py`
- `backend/main.py`
- `data/samples/jd_samples.json`
- `data/samples/resume_samples.json`
- `data/outputs/jd_raw.jsonl`
- `data/outputs/jd_raw.csv`
- `data/outputs/jd_raw_summary.json`

## 冯轩宇

职责：

- 前端
- 后端相关接口
- 数据库
- 项目结构

## 喻昕之负责的内容

### JD 数据输入层

- `data/samples/jd_data_source_plan.md`
- `backend/scrapers.py`

### JD 解析与标准化层

- `backend/parsers.py`
- `backend/skill_normalizer.py`
- `backend/schemas.py`
- `backend/config.py`

### JD 输出层

- `backend/main.py`
- `data/outputs/jd_raw.jsonl`
- `data/outputs/jd_raw.csv`
- `data/outputs/jd_raw_summary.json`

### 样例与验证数据

- `data/samples/jd_samples.json`
- `data/samples/resume_samples.json`
