"""Static skill catalog, aliases, relations, and taxonomy mappings."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple


def skill_id_for(name: str) -> str:
    text = re.sub(r"\s+", "_", name.strip().lower())
    text = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff+#.-]+", "", text)
    return f"skill:{text}"


def _skill(name: str, skill_type: str, aliases: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "skill_id": skill_id_for(name),
        "name": name,
        "skill_type": skill_type,
        "aliases": sorted({name, *aliases}, key=len, reverse=True),
    }


SKILL_CATALOG: Dict[str, Dict[str, Any]] = {
    item["name"]: item
    for item in [
        _skill("Python", "编程语言", ["python", "PYTHON"]),
        _skill("Java", "编程语言", ["java", "JAVA"]),
        _skill("C++", "编程语言", ["c++", "C Plus Plus", "cpp", "Cplusplus"]),
        _skill("C#", "编程语言", ["c#", "C Sharp"]),
        _skill("Go", "编程语言", ["golang", "Golang", "go"]),
        _skill("JavaScript", "编程语言", ["javascript", "JS", "js"]),
        _skill("TypeScript", "编程语言", ["typescript", "TS", "ts"]),
        _skill("SQL", "编程语言", ["sql", "MySQL SQL"]),
        _skill("R", "编程语言", ["R语言", "r language"]),
        _skill("Scala", "编程语言", ["scala"]),
        _skill("Shell", "编程语言", ["shell", "Bash", "bash"]),
        _skill("PyTorch", "框架工具", ["pytorch", "Pytorch", "torch", "Torch"]),
        _skill("TensorFlow", "框架工具", ["tensorflow", "Tensorflow", "TF"]),
        _skill("Keras", "框架工具", ["keras"]),
        _skill("Scikit-learn", "框架工具", ["sklearn", "scikit learn", "Scikit Learn"]),
        _skill("Pandas", "框架工具", ["pandas"]),
        _skill("NumPy", "框架工具", ["numpy", "Numpy"]),
        _skill("Spark", "框架工具", ["spark", "Apache Spark"]),
        _skill("Hadoop", "框架工具", ["hadoop"]),
        _skill("Flink", "框架工具", ["flink"]),
        _skill("Kafka", "框架工具", ["kafka"]),
        _skill("Redis", "框架工具", ["redis"]),
        _skill("MySQL", "框架工具", ["mysql"]),
        _skill("PostgreSQL", "框架工具", ["postgresql", "Postgres"]),
        _skill("MongoDB", "框架工具", ["mongodb", "Mongo"]),
        _skill("Docker", "框架工具", ["docker"]),
        _skill("Kubernetes", "框架工具", ["kubernetes", "K8s", "k8s"]),
        _skill("Git", "框架工具", ["git"]),
        _skill("Linux", "框架工具", ["linux"]),
        _skill("Spring Boot", "框架工具", ["spring boot", "SpringBoot", "springboot"]),
        _skill("Vue", "框架工具", ["vue", "Vue.js", "vuejs"]),
        _skill("React", "框架工具", ["react", "React.js", "reactjs"]),
        _skill("FastAPI", "框架工具", ["fastapi", "Fast API"]),
        _skill("Flask", "框架工具", ["flask"]),
        _skill("Django", "框架工具", ["django"]),
        _skill("LangChain", "框架工具", ["langchain", "Lang Chain"]),
        _skill("LlamaIndex", "框架工具", ["llamaindex", "Llama Index"]),
        _skill("Elasticsearch", "框架工具", ["elastic search", "ES", "ElasticSearch"]),
        _skill("Milvus", "框架工具", ["milvus"]),
        _skill("Neo4j", "框架工具", ["neo4j"]),
        _skill("Airflow", "框架工具", ["airflow"]),
        _skill("机器学习", "算法能力", ["ML", "Machine Learning", "machine learning"]),
        _skill("深度学习", "算法能力", ["DL", "Deep Learning", "deep learning"]),
        _skill("推荐算法", "算法能力", ["推荐系统", "recommendation", "推荐模型"]),
        _skill("NLP", "算法能力", ["自然语言处理", "Natural Language Processing", "nlp"]),
        _skill("计算机视觉", "算法能力", ["CV", "Computer Vision", "图像算法"]),
        _skill("知识图谱", "算法能力", ["KG", "Knowledge Graph", "knowledge graph"]),
        _skill("大语言模型", "算法能力", ["大模型", "LLM", "LLMs", "Large Language Model", "AIGC"]),
        _skill("RAG", "算法能力", ["rag", "检索增强生成", "Retrieval Augmented Generation"]),
        _skill("大模型微调", "算法能力", ["模型微调", "指令微调", "SFT", "LoRA", "lora"]),
        _skill("召回模型", "算法能力", ["召回", "召回算法", "双塔召回"]),
        _skill("排序模型", "算法能力", ["排序", "精排", "Learning to Rank"]),
        _skill("搜索算法", "算法能力", ["搜索", "检索算法"]),
        _skill("Transformer", "算法能力", ["transformer", "Transformers"]),
        _skill("CNN", "算法能力", ["卷积神经网络", "Convolutional Neural Network"]),
        _skill("BERT", "算法能力", ["bert"]),
        _skill("图神经网络", "算法能力", ["GNN", "Graph Neural Network"]),
        _skill("模型训练", "算法能力", ["训练模型", "模型训练流程"]),
        _skill("模型优化", "算法能力", ["模型调优", "调参", "算法优化"]),
        _skill("特征工程", "算法能力", ["Feature Engineering", "feature engineering"]),
        _skill("A/B测试", "算法能力", ["AB测试", "A/B Test", "ab test"]),
        _skill("数据分析", "数据能力", ["数据分析", "Data Analysis"]),
        _skill("数据挖掘", "数据能力", ["Data Mining", "data mining"]),
        _skill("数据仓库", "数据能力", ["数仓", "Data Warehouse", "DWH"]),
        _skill("数据治理", "数据能力", ["Data Governance", "data governance"]),
        _skill("ETL", "数据能力", ["etl"]),
        _skill("BI", "数据能力", ["商业智能", "Business Intelligence"]),
        _skill("可视化", "数据能力", ["数据可视化", "Visualization", "Tableau", "PowerBI"]),
        _skill("系统设计", "工程能力", ["架构设计", "System Design"]),
        _skill("接口开发", "工程能力", ["API开发", "接口设计", "RESTful"]),
        _skill("性能优化", "工程能力", ["性能调优", "高性能"]),
        _skill("分布式系统", "工程能力", ["分布式", "Distributed System"]),
        _skill("微服务", "工程能力", ["Microservice", "microservices"]),
        _skill("后端开发", "工程能力", ["服务端开发", "Backend", "backend"]),
        _skill("前端开发", "工程能力", ["Frontend", "frontend"]),
        _skill("云原生", "工程能力", ["Cloud Native", "cloud native"]),
        _skill("DevOps", "工程能力", ["devops"]),
        _skill("CI/CD", "工程能力", ["cicd", "CI CD", "持续集成", "持续交付"]),
        _skill("MLOps", "工程能力", ["mlops"]),
        _skill("模型部署", "工程能力", ["模型上线", "推理服务", "Serving"]),
        _skill("工程化", "工程能力", ["工程落地", "产品化", "落地能力"]),
        _skill("高并发", "工程能力", ["高并发系统", "并发优化"]),
        _skill("用户增长", "业务能力", ["增长", "增长分析"]),
        _skill("风控", "业务能力", ["风险控制", "反欺诈"]),
        _skill("供应链", "业务能力", ["Supply Chain"]),
        _skill("招聘业务", "业务能力", ["招聘", "人力资源", "HR"]),
        _skill("金融", "业务能力", ["银行", "保险", "证券", "FinTech"]),
        _skill("医疗", "业务能力", ["Healthcare", "医药"]),
        _skill("制造", "业务能力", ["工业", "智能制造"]),
        _skill("教育", "业务能力", ["在线教育", "教培"]),
        _skill("电商", "业务能力", ["电子商务", "零售"]),
        _skill("企业服务", "业务能力", ["ToB", "SaaS", "企业级"]),
        _skill("内容推荐", "业务能力", ["内容分发", "信息流"]),
        _skill("知识库问答", "业务能力", ["知识问答", "问答系统", "QA系统"]),
        _skill("沟通协作", "通用能力", ["沟通", "协作", "跨部门"]),
        _skill("项目管理", "通用能力", ["项目推进", "进度管理"]),
        _skill("文档能力", "通用能力", ["文档", "技术文档"]),
        _skill("学习能力", "通用能力", ["快速学习", "自驱学习"]),
        _skill("团队管理", "通用能力", ["团队负责人", "带团队"]),
        _skill("需求分析", "通用能力", ["需求梳理", "业务分析"]),
    ]
}


ALIAS_TO_SKILL: Dict[str, str] = {}
for skill_name, skill_info in SKILL_CATALOG.items():
    for alias in skill_info["aliases"]:
        ALIAS_TO_SKILL[alias] = skill_name
        if re.search(r"[A-Za-z]", alias):
            ALIAS_TO_SKILL[alias.lower()] = skill_name


SKILL_RELATIONS: Dict[str, List[Tuple[str, str]]] = {
    "机器学习": [("Scikit-learn", "child"), ("特征工程", "related"), ("数据挖掘", "related"), ("推荐算法", "related"), ("模型训练", "related")],
    "深度学习": [("PyTorch", "tool"), ("TensorFlow", "tool"), ("CNN", "child"), ("Transformer", "child"), ("BERT", "child"), ("大语言模型", "child")],
    "推荐算法": [("召回模型", "child"), ("排序模型", "child"), ("内容推荐", "related"), ("搜索算法", "related"), ("A/B测试", "related")],
    "NLP": [("BERT", "child"), ("Transformer", "related"), ("大语言模型", "related"), ("知识图谱", "related")],
    "知识图谱": [("Neo4j", "tool"), ("NLP", "related"), ("RAG", "related"), ("知识库问答", "related")],
    "大语言模型": [("RAG", "related"), ("大模型微调", "child"), ("Transformer", "related"), ("LangChain", "tool"), ("LlamaIndex", "tool")],
    "RAG": [("大语言模型", "related"), ("LangChain", "tool"), ("LlamaIndex", "tool"), ("Elasticsearch", "tool"), ("Milvus", "tool"), ("知识库问答", "related")],
    "数据分析": [("SQL", "tool"), ("Pandas", "tool"), ("可视化", "related"), ("BI", "related")],
    "数据仓库": [("SQL", "tool"), ("ETL", "related"), ("Spark", "tool"), ("Hadoop", "tool")],
    "后端开发": [("Java", "language"), ("Python", "language"), ("Spring Boot", "tool"), ("FastAPI", "tool"), ("接口开发", "related"), ("微服务", "related")],
    "前端开发": [("JavaScript", "language"), ("TypeScript", "language"), ("Vue", "tool"), ("React", "tool")],
    "分布式系统": [("Spark", "tool"), ("Kafka", "tool"), ("Redis", "tool"), ("高并发", "related"), ("微服务", "related")],
    "模型部署": [("Docker", "tool"), ("Kubernetes", "tool"), ("MLOps", "related"), ("FastAPI", "tool")],
    "工程化": [("Docker", "tool"), ("Kubernetes", "tool"), ("CI/CD", "related"), ("DevOps", "related"), ("模型部署", "related")],
}

RELATED_LOOKUP: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
for source, targets in SKILL_RELATIONS.items():
    for target, relation in targets:
        RELATED_LOOKUP[source].append((target, relation))
        reverse_relation = "parent" if relation == "child" else "related"
        RELATED_LOOKUP[target].append((source, reverse_relation))


JD_SECTION_HEADERS: Dict[str, str] = {
    "岗位名称": "job_title",
    "职位名称": "job_title",
    "招聘职位": "job_title",
    "职位": "job_title",
    "job title": "job_title",
    "岗位职责": "responsibilities",
    "工作职责": "responsibilities",
    "职位职责": "responsibilities",
    "你将负责": "responsibilities",
    "responsibilities": "responsibilities",
    "任职要求": "requirements",
    "岗位要求": "requirements",
    "能力要求": "requirements",
    "职位要求": "requirements",
    "requirements": "requirements",
    "加分项": "preferred",
    "优先条件": "preferred",
    "优先": "preferred",
    "bonus": "preferred",
    "preferred": "preferred",
    "学历要求": "education",
    "教育背景": "education",
    "工作年限": "experience",
    "经验要求": "experience",
    "行业背景": "domain",
    "业务背景": "domain",
}

RESUME_SECTION_HEADERS: Dict[str, str] = {
    "基本信息": "basic_info",
    "个人信息": "basic_info",
    "姓名": "basic_info",
    "求职意向": "target_position",
    "目标岗位": "target_position",
    "期望职位": "target_position",
    "教育经历": "education",
    "教育背景": "education",
    "工作经历": "work_experiences",
    "实习经历": "work_experiences",
    "任职公司": "work_experiences",
    "项目经历": "projects",
    "项目经验": "projects",
    "项目介绍": "projects",
    "项目职责": "projects",
    "专业技能": "skills",
    "技能栈": "skills",
    "掌握技能": "skills",
    "技能清单": "skills",
    "证书": "certificates",
    "论文": "certificates",
    "专利": "certificates",
    "竞赛": "certificates",
    "开源": "certificates",
}

DEGREE_ORDER = {
    "高中": 0,
    "中专": 0,
    "大专": 1,
    "专科": 1,
    "本科": 2,
    "学士": 2,
    "硕士": 3,
    "研究生": 3,
    "博士": 4,
    "PhD": 4,
}

JD_VERBS = ("负责", "参与", "建设", "设计", "开发", "维护", "优化", "推动", "搭建", "落地", "迭代")
REQUIREMENT_WORDS = ("熟悉", "熟练", "掌握", "精通", "具备", "要求", "经验", "本科", "硕士", "博士", "学历")
PREFERRED_WORDS = ("优先", "加分", "最好", "bonus", "preferred", "有相关经验者优先")
DOMAIN_KEYWORDS = ("金融", "医疗", "制造", "教育", "电商", "招聘", "风控", "供应链", "企业服务", "SaaS", "ToB", "内容推荐", "知识库问答")


CAPABILITY_DOMAIN_MAPPING: Dict[str, str] = {
    "编程语言": "工程实现能力",
    "框架工具": "技术栈应用能力",
    "算法能力": "智能算法能力",
    "数据能力": "数据处理与分析能力",
    "工程能力": "软件工程能力",
    "业务能力": "行业业务理解能力",
    "通用能力": "职业通用能力",
}

TECH_STACK_MAPPING: Dict[str, List[str]] = {
    "AI/算法栈": ["Python", "PyTorch", "TensorFlow", "Keras", "Scikit-learn", "Transformer", "BERT", "RAG", "大语言模型"],
    "大数据栈": ["SQL", "Spark", "Hadoop", "Flink", "Kafka", "数据仓库", "ETL"],
    "后端工程栈": ["Java", "Python", "Spring Boot", "FastAPI", "Flask", "Django", "MySQL", "Redis", "微服务"],
    "前端工程栈": ["JavaScript", "TypeScript", "Vue", "React"],
    "云原生/MLOps栈": ["Docker", "Kubernetes", "DevOps", "CI/CD", "MLOps", "模型部署"],
}
