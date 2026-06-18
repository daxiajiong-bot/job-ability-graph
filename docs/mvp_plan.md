
# MVP Plan

## 1. 项目一句话目标

本项目面向“多源异构数据驱动岗位和能力图谱构建与动态演化分析”赛题，第一阶段先实现一个最小 Demo：输入岗位 JD 和简历文本，系统完成结构化解析、人岗匹配、能力差距分析，并生成岗位—能力关系图谱。

## 2. 第一版 Demo 范围

### 输入

1. 一段岗位 JD 文本
2. 一段简历文本

### 输出

1. JD 结构化解析结果
2. 简历结构化解析结果
3. 人岗匹配分数
4. 匹配理由
5. 缺失技能
6. 岗位—技能图谱展示

## 3. 第一版暂不做

1. 大规模爬虫
2. 复杂训练模型
3. 复杂前端
4. 多用户系统
5. 登录注册
6. 真正的大规模动态图谱

## 4. JD 解析 JSON 格式

{
  "job_title": "大模型算法工程师",
  "education": "硕士",
  "experience_years": 3,
  "skills": ["Python", "PyTorch", "RAG", "大模型微调"],
  "responsibilities": ["负责大模型微调", "负责知识库问答系统建设"],
  "industry": "人工智能"
}

## 5. 简历解析 JSON 格式

{
  "education": "硕士",
  "experience_years": 1,
  "skills": ["Python", "PyTorch", "SQL", "RAG"],
  "projects": [
    {
      "name": "企业知识库问答系统",
      "skills": ["Python", "RAG", "LangChain"]
    }
  ]
}

## 6. 匹配结果JSON格式

{
  "match_score": 82.5,
  "matched_skills": ["Python", "PyTorch", "RAG"],
  "missing_skills": ["Docker", "Kubernetes"],
  "explanation": "候选人在算法和 RAG 方向匹配较好，但工程部署能力不足。"
}
