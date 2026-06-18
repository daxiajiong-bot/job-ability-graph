# 团队分工与文件归类

下面按你们当前分工，把仓库里的文件和职责对齐。

## 王贤炯
职责：
- 技术路线统筹
- JobFormer 论文复现
- Prompt、Skill 编写
- 新岗位发现算法、岗位能力动态更新

对应内容：
- `algorithms/matcher.py`
- 后续的 `algorithms/` 新模块
- 后续的 `prompts/`、`experiments/`

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

对应内容：
- 后续的 `frontend/`
- 后续的 `database/`、`migrations/`
- 后续把 `backend/main.py` 从 CLI 扩展为 API 服务

## 你负责的这条线

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

## 一句话边界

- JD 原始抓取、解析、技能抽取、技能词表、结构化输出：喻昕之
- 模型、算法、动态演化：王贤炯
- 接口、前端、数据库、工程结构：冯轩宇
