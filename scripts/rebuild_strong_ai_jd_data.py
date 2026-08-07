#!/usr/bin/env python3
"""Rebuild JD data with only strongly AI/ML-related positions."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import importlib.util
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "append_ai_jd_data.py"
JD_JSONL = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
JD_CSV = REPO_ROOT / "data" / "small-raw" / "jd_raw.csv"
JD_SUMMARY = REPO_ROOT / "data" / "small-raw" / "jd_raw_summary.json"
FETCH_ROOT = REPO_ROOT / "data" / "small-raw" / "_jd_ai_fetch_tmp"

STRONG_KEYWORDS = [
    "机器学习",
    "机器学习工程师",
    "机器学习算法",
    "深度学习",
    "深度学习工程师",
    "深度学习算法",
    "大模型",
    "大模型开发工程师",
    "大模型应用开发工程师",
    "大模型算法工程师",
    "大模型工程师",
    "大模型研发工程师",
    "大语言模型",
    "算法工程师",
    "算法研究员",
    "算法研发",
    "AI算法",
    "人工智能工程师",
    "人工智能算法",
    "自然语言处理",
    "自然语言处理工程师",
    "NLP",
    "NLP算法工程师",
    "计算机视觉",
    "计算机视觉工程师",
    "图像算法",
    "图像算法工程师",
    "视觉算法",
    "视觉算法工程师",
    "推荐算法",
    "推荐算法工程师",
    "搜索算法",
    "搜索算法工程师",
    "数据挖掘",
    "多模态",
    "多模态算法工程师",
    "LLM",
    "LLM工程师",
    "LLM算法",
    "PyTorch",
    "TensorFlow",
    "模型训练",
    "模型微调",
    "模型部署工程师",
    "模型推理工程师",
    "模型工程师",
    "RAG",
    "RAG开发工程师",
    "知识图谱",
    "知识图谱工程师",
    "强化学习",
    "强化学习工程师",
    "目标检测",
    "语音识别",
    "语音识别工程师",
    "机器视觉",
    "机器视觉工程师",
    "人工智能研发",
    "AI工程师",
    "AI开发工程师",
    "AI应用开发",
    "AI应用工程师",
    "AI研发工程师",
    "AI Agent",
    "Agent开发工程师",
    "智能体开发",
    "具身智能",
    "数据科学家",
    "Data Scientist",
    "MLOps",
    "AI Infra",
    "OCR算法",
    "人脸识别",
    "大模型应用开发",
    "算法",
    "算法开发",
    "算法专家",
    "算法科学家",
    "人工智能",
    "AI",
    "AI技术专家",
    "AI架构师",
    "智能算法",
    "神经网络",
    "Transformer",
    "LangChain",
    "LangGraph",
    "智能体",
    "多模态大模型",
    "视觉大模型",
    "计算机视觉算法",
    "CV算法",
    "NLP工程师",
    "语音算法",
    "推荐系统",
    "搜索推荐",
    "数据科学",
    "数据挖掘工程师",
]

CORE_TERMS = [
    "机器学习",
    "深度学习",
    "大模型",
    "算法",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "视觉算法",
    "推荐算法",
    "搜索算法",
    "语音算法",
    "数据挖掘",
    "多模态",
    "LLM",
    "PyTorch",
    "TensorFlow",
    "模型训练",
    "模型微调",
    "模型部署",
    "模型推理",
    "推理优化",
    "微调",
    "RAG",
    "强化学习",
    "知识图谱",
    "目标检测",
    "语音识别",
    "机器视觉",
    "数据科学",
    "智能算法",
    "生成式AI算法",
    "Machine Learning",
    "ML Engineer",
    "Deep Learning",
    "Artificial Intelligence",
    "AI Engineer",
    "AI Scientist",
    "Applied Scientist",
    "Large Language",
    "Natural Language Processing",
    "Computer Vision",
    "Data Scientist",
    "Data Science",
    "Model Training",
    "Model Deployment",
    "MLOps",
    "GenAI",
    "Generative AI",
    "Reinforcement Learning",
    "Recommender",
]

TITLE_STRONG_TERMS = [
    "算法",
    "机器学习",
    "深度学习",
    "大模型",
    "自然语言处理",
    "NLP",
    "计算机视觉",
    "图像算法",
    "视觉算法",
    "推荐算法",
    "搜索算法",
    "语音算法",
    "数据挖掘",
    "多模态",
    "LLM",
    "模型训练",
    "模型微调",
    "RAG",
    "强化学习",
    "知识图谱",
    "目标检测",
    "机器视觉",
    "AI研发",
    "人工智能研发",
    "AI工程师",
    "人工智能工程师",
    "AI应用工程师",
    "AI开发工程师",
    "AI Agent工程师",
    "AI Agent 产品",
    "AI产品经理",
    "AI 产品经理",
    "大模型产品经理",
    "人工智能产品经理",
    "大模型评测",
    "大模型数据",
    "数据标注工程师",
    "模型评测",
    "AI平台",
    "AI安全",
    "AI应用",
    "AI自动化",
    "AI全栈",
    "AI原生产品",
    "AI产品负责人",
    "AI互联网产品经理",
    "AI项目经理",
    "AI 项目经理",
    "人工智能项目经理",
    "人工智能程序员",
    "人工智能技术助理",
    "人工智能测试",
    "人工智能产品调测",
    "人工智能与无线通信",
    "电力人工智能",
    "人工智能研究",
    "材料人工智能",
    "Pytorch",
    "视觉专家",
    "端侧 AI",
    "AI大模型",
    "大模型全链路",
    "AI Agent 研发",
    "提示词工程师",
    "数据科学家",
    "Machine Learning",
    "ML Engineer",
    "Deep Learning",
    "AI Engineer",
    "AI Scientist",
    "Applied Scientist",
    "Data Scientist",
    "Computer Vision",
    "MLOps",
    "GenAI",
    "Generative AI",
]

TECH_TITLE_TERMS = [
    "工程师",
    "开发",
    "研发",
    "研究员",
    "科学家",
    "架构师",
    "技术专家",
    "博士后",
    "实习生",
    "分析师",
    "Engineer",
    "Scientist",
    "Researcher",
    "Developer",
    "Architect",
    "Analyst",
    "MLOps",
    "Data Engineer",
    "Applied Scientist",
]

WEAK_TITLE_TERMS = [
    "AIGC",
    "前端",
    "后端",
    "全栈",
    "软件测试",
    "测试开发",
    "测试工程师",
    "测试助理",
    "测试",
    "Frontend",
    "Front End",
    "Backend",
    "Back End",
    "Full Stack",
    "Fullstack",
    "QA",
    "Quality Engineer",
    "Test Engineer",
    "Testing",
    "SDET",
    "销售",
    "售前",
    "售后",
    "顾问",
    "咨询",
    "客服",
    "运营",
    "产品经理",
    "产品负责人",
    "项目经理",
    "项目管理",
    "项目主管",
    "数据标注",
    "标注",
    "训练师",
    "音频转写",
    "对话改写",
    "内容审核",
    "数据分析师",
    "行政",
    "兼职",
    "暑假工",
    "教师",
    "老师",
    "讲师",
    "助教",
    "招生",
    "市场",
    "商务",
    "编导",
    "导演",
    "短剧",
    "设计师",
    "画师",
    "美工",
    "主播",
    "文案",
    "剪辑",
    "视频制作",
    "内容制作",
    "管培",
    "课程",
    "教培",
    "外观结构",
    "Sales",
    "Marketing",
    "Customer",
    "Support",
    "Account Executive",
    "Recruiter",
    "Copywriter",
    "Content",
    "Designer",
    "Product Manager",
    "Product Owner",
    "Project Manager",
    "Program Manager",
    "Data Analyst",
    "Business Analyst",
    "Product Analyst",
    "Marketing Analyst",
    "Financial Analyst",
    "Operations Analyst",
    "Business Intelligence",
    "Community",
    "SEO",
    "Coordinator",
    "Assistant",
]

def term_pattern(term: str) -> str:
    escaped = re.escape(term)
    if re.search(r"[A-Za-z]", term):
        return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return escaped


CORE_RE = re.compile("|".join(term_pattern(term) for term in CORE_TERMS), re.IGNORECASE)
TITLE_STRONG_RE = re.compile("|".join(term_pattern(term) for term in TITLE_STRONG_TERMS), re.IGNORECASE)
TECH_TITLE_RE = re.compile("|".join(term_pattern(term) for term in TECH_TITLE_TERMS), re.IGNORECASE)
WEAK_TITLE_RE = re.compile("|".join(term_pattern(term) for term in WEAK_TITLE_TERMS), re.IGNORECASE)

SOFT_TECH_WEAK_TITLE_TERMS = [
    "前端",
    "后端",
    "全栈",
    "软件测试",
    "测试开发",
    "测试工程师",
    "测试助理",
    "测试",
    "Frontend",
    "Front End",
    "Backend",
    "Back End",
    "Full Stack",
    "Fullstack",
    "QA",
    "Quality Engineer",
    "Test Engineer",
    "Testing",
    "SDET",
    "数据分析师",
    "Data Analyst",
    "Business Analyst",
    "Business Intelligence",
]

HARD_WEAK_TITLE_TERMS = [term for term in WEAK_TITLE_TERMS if term not in set(SOFT_TECH_WEAK_TITLE_TERMS)]
HARD_WEAK_TITLE_RE = re.compile("|".join(term_pattern(term) for term in HARD_WEAK_TITLE_TERMS), re.IGNORECASE)
SOFT_TECH_WEAK_TITLE_RE = re.compile(
    "|".join(term_pattern(term) for term in SOFT_TECH_WEAK_TITLE_TERMS),
    re.IGNORECASE,
)

REQUIRED_TITLE_TERMS = [
    "人工智能",
    "机器学习",
    "算法",
    "大模型",
    "大语言模型",
    "自然语言处理",
    "计算机视觉",
    "NLP",
    "CV",
    "LLM",
    "深度学习",
    "AI",
    "Machine Learning",
    "ML",
    "Algorithm",
    "Algorithms",
    "Deep Learning",
    "Large Language Model",
    "Large Language Models",
    "Natural Language Processing",
    "Computer Vision",
    "Artificial Intelligence",
    "AI/ML",
    "AIML",
]

REQUIRED_TITLE_RE = re.compile("|".join(term_pattern(term) for term in REQUIRED_TITLE_TERMS), re.IGNORECASE)

AI_DOMAIN_TERMS = [
    "人工智能",
    "机器学习",
    "深度学习",
    "大模型",
    "大语言模型",
    "自然语言处理",
    "计算机视觉",
    "机器视觉",
    "图像算法",
    "视觉算法",
    "图像识别",
    "目标检测",
    "多模态",
    "推荐算法",
    "搜索算法",
    "搜索/推荐",
    "强化学习",
    "知识图谱",
    "语音识别",
    "神经网络",
    "智能算法",
    "数据挖掘",
    "模型训练",
    "模型微调",
    "模型部署",
    "模型推理",
    "智能体",
    "AI",
    "NLP",
    "CV",
    "LLM",
    "RAG",
    "Agent",
    "PyTorch",
    "TensorFlow",
    "Transformer",
    "Machine Learning",
    "Deep Learning",
    "Artificial Intelligence",
    "Computer Vision",
    "Natural Language Processing",
    "Generative AI",
    "GenAI",
    "Reinforcement Learning",
]

ENGINEERING_TITLE_TERMS = [
    "工程师",
    "开发",
    "研发",
    "算法",
    "研究员",
    "研究",
    "博士后",
    "科学家",
    "架构师",
    "专家",
    "技术",
    "技术专家",
    "建模",
    "Engineer",
    "Developer",
    "Scientist",
    "Researcher",
    "Architect",
]

NON_AI_TECH_TITLE_TERMS = [
    "电机控制",
    "伺服",
    "无线通信",
    "通信算法",
    "调度算法",
    "AGV",
    "运筹优化",
    "仿真算法",
    "数控算法",
    "FPGA",
    "CT算法",
    "重建",
    "信号处理",
    "地图算法",
    "导航算法",
    "定位算法",
    "卫星",
    "机械臂控制",
    "工业机器人",
    "ISP算法",
    "SLAM",
    "ROS",
]

AI_DOMAIN_RE = re.compile("|".join(term_pattern(term) for term in AI_DOMAIN_TERMS), re.IGNORECASE)
AI_DOMAIN_TERM_RES = [re.compile(term_pattern(term), re.IGNORECASE) for term in AI_DOMAIN_TERMS]
ENGINEERING_TITLE_RE = re.compile("|".join(term_pattern(term) for term in ENGINEERING_TITLE_TERMS), re.IGNORECASE)
NON_AI_TECH_TITLE_RE = re.compile("|".join(term_pattern(term) for term in NON_AI_TECH_TITLE_TERMS), re.IGNORECASE)
NONTECH_EVAL_RE = re.compile(r"训练|测评|评测|评估|测试")

# These roles may mention or use AI, but their primary work is not AI software,
# algorithm, model, or agent development.
NON_DEVELOPMENT_TITLE_TERMS = [
    "营销",
    "渠道",
    "解决方案",
    "顾问",
    "咨询",
    "运营",
    "办公助理",
    "产品经理",
    "产品负责人",
    "产品总监",
    "产品助理",
    "产品专员",
    "项目经理",
    "项目管理",
    "数据分析师",
    "业务分析师",
    "分析专员",
    "分析师",
    "美术",
    "美工",
    "画师",
    "动漫",
    "动画",
    "制作师",
    "内容创作",
    "内容策划",
    "技术员",
    "调试",
    "专员",
    "标注",
    "审核",
    "测评",
    "评测",
    "评估",
    "测试",
    "检测员",
    "质检",
    "质控",
    "训练师",
    "实施",
    "交付",
    "技术支持",
    "客户成功",
    "赋能师",
    "赋能专员",
    "预算员",
    "造价工程师",
    "Sales",
    "Marketing",
    "Solution",
    "Consultant",
    "Operations",
    "Data Analyst",
    "Business Analyst",
    "Designer",
    "Artist",
    "Animator",
    "Tester",
    "Testing",
    "Support",
]

SPECIFIC_AI_TITLE_TERMS = [
    "机器学习",
    "深度学习",
    "大模型",
    "大语言模型",
    "自然语言处理",
    "计算机视觉",
    "机器视觉",
    "图像算法",
    "视觉算法",
    "图像识别",
    "目标检测",
    "多模态",
    "推荐算法",
    "推荐系统",
    "搜索算法",
    "搜索推荐",
    "强化学习",
    "知识图谱",
    "语音识别",
    "语音算法",
    "神经网络",
    "数据挖掘",
    "模型训练",
    "模型微调",
    "模型推理",
    "模型部署",
    "推理优化",
    "智能体开发",
    "智能体研发",
    "智能体算法",
    "智能体",
    "Agent开发",
    "Agent研发",
    "AI Agent",
    "Agent",
    "具身智能",
    "自动驾驶算法",
    "智能驾驶算法",
    "MLOps",
    "AI Infra",
    "NLP",
    "LLM",
    "RAG",
    "OCR",
    "ASR",
    "TTS",
    "Data Scientist",
    "Applied Scientist",
    "Machine Learning",
    "Deep Learning",
    "Computer Vision",
    "Generative AI",
    "GenAI",
    "Reinforcement Learning",
]

DEVELOPMENT_TITLE_TERMS = [
    "工程师",
    "开发",
    "研发",
    "算法",
    "研究员",
    "研究",
    "博士后",
    "科学家",
    "架构师",
    "技术专家",
    "程序员",
    "全栈",
    "后端",
    "软件",
    "平台",
    "建模",
    "部署",
    "推理",
    "实习生",
    "Engineer",
    "Developer",
    "Scientist",
    "Researcher",
    "Architect",
]

AI_TECHNICAL_EVIDENCE_GROUPS = [
    ["机器学习", "深度学习", "监督学习", "无监督学习", "分类模型", "回归模型", "聚类算法"],
    ["PyTorch", "TensorFlow", "MindSpore", "PaddlePaddle", "JAX", "scikit-learn", "XGBoost"],
    ["模型训练", "预训练", "微调", "LoRA", "SFT", "DPO", "RLHF", "蒸馏", "量化"],
    ["模型推理", "推理优化", "推理服务", "vLLM", "SGLang", "TensorRT", "ONNX", "CUDA"],
    ["大语言模型", "大模型", "LLM", "Transformer", "BERT", "GPT", "Qwen", "DeepSeek"],
    ["RAG", "Embedding", "向量数据库", "向量检索", "Milvus", "FAISS", "Rerank"],
    [
        "Function Calling",
        "Tool Calling",
        "多Agent",
        "多智能体",
        "Agent框架",
        "智能体框架",
        "LangChain",
        "LangGraph",
        "LlamaIndex",
        "AutoGen",
        "CrewAI",
        "MCP",
    ],
    ["计算机视觉", "目标检测", "图像识别", "图像分割", "OpenCV", "YOLO", "卷积神经网络", "CNN"],
    ["自然语言处理", "NLP", "文本分类", "命名实体识别", "信息抽取", "语义匹配"],
    ["推荐系统", "推荐算法", "搜索算法", "排序模型", "召回模型", "CTR", "Learning to Rank"],
    ["语音识别", "语音合成", "语音算法", "ASR", "TTS", "声学模型"],
    ["强化学习", "知识图谱", "多模态", "扩散模型", "Diffusion", "生成对抗网络", "GAN"],
]

NON_DEVELOPMENT_TITLE_RE = re.compile(
    "|".join(term_pattern(term) for term in NON_DEVELOPMENT_TITLE_TERMS),
    re.IGNORECASE,
)
SPECIFIC_AI_TITLE_RE = re.compile(
    "|".join(term_pattern(term) for term in SPECIFIC_AI_TITLE_TERMS),
    re.IGNORECASE,
)
DEVELOPMENT_TITLE_RE = re.compile(
    "|".join(term_pattern(term) for term in DEVELOPMENT_TITLE_TERMS),
    re.IGNORECASE,
)
ALGORITHM_TITLE_RE = re.compile(r"算法|模型(?:工程师|研发|开发|科学家|专家)", re.IGNORECASE)
OPENCLAW_RE = re.compile(r"(?:openclaw|0penclaw|龙虾)", re.IGNORECASE)
OPENCLAW_DEVELOPMENT_RE = re.compile(
    r"二次开发|源码|深度定制|重构|核心模块|runtime|executor|skill(?:s)?开发|"
    r"智能体(?:系统|平台|框架|开发|研发)|agent(?:系统|平台|框架|开发|研发)|"
    r"function calling|tool calling|多agent|多智能体|langchain|langgraph|llamaindex|autogen|crewai|mcp",
    re.IGNORECASE,
)
AI_BUILD_ACTION_RE = re.compile(
    r"开发|研发|设计并实现|设计与实现|构建|训练|预训练|微调|推理|部署|工程化|"
    r"架构设计|二次开发|重构|编程|代码|建模|算法优化|模型优化",
    re.IGNORECASE,
)
AI_TECHNICAL_EVIDENCE_RES = [
    re.compile("|".join(term_pattern(term) for term in group), re.IGNORECASE)
    for group in AI_TECHNICAL_EVIDENCE_GROUPS
]

ZHAOPIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://sou.zhaopin.com/",
}


@dataclass(frozen=True)
class NationalFetchTask:
    keyword: str
    page: int
    city_code: str = "all"
    city_name: str = "全国"

    @property
    def url(self) -> str:
        keyword = quote(self.keyword)
        return f"https://sou.zhaopin.com/?kw={keyword}&kt=3&p={self.page}"

    @property
    def cache_path(self) -> Path:
        safe_keyword = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", self.keyword)
        return FETCH_ROOT / f"{self.city_code}_{safe_keyword}_{self.page:03d}.html"


@dataclass(frozen=True)
class CachedFetchTask:
    keyword: str
    city_code: str
    city_name: str
    page: int
    cached_path: Path

    @property
    def url(self) -> str:
        return ""

    @property
    def cache_path(self) -> Path:
        return self.cached_path


SEARCH_CITIES = {
    "530": "北京",
    "538": "上海",
    "763": "广州",
    "765": "深圳",
    "653": "杭州",
    "801": "成都",
    "635": "南京",
    "736": "武汉",
    "854": "西安",
    "531": "天津",
    "639": "苏州",
    "551": "重庆",
    "664": "合肥",
    "702": "济南",
    "703": "青岛",
    "600": "大连",
    "599": "沈阳",
    "719": "郑州",
    "749": "长沙",
    "654": "宁波",
    "636": "无锡",
    "682": "厦门",
    "681": "福州",
    "768": "佛山",
    "779": "东莞",
    "766": "珠海",
    "780": "中山",
    "773": "惠州",
    "638": "常州",
    "641": "南通",
    "637": "徐州",
    "831": "昆明",
    "691": "南昌",
    "822": "贵阳",
    "613": "长春",
    "622": "哈尔滨",
    "565": "石家庄",
    "576": "太原",
    "785": "南宁",
    "864": "兰州",
    "890": "乌鲁木齐",
    "799": "海口",
    "587": "呼和浩特",
    "886": "银川",
    "878": "西宁",
    "655": "温州",
    "656": "嘉兴",
    "658": "绍兴",
    "659": "金华",
    "662": "台州",
    "707": "烟台",
    "708": "潍坊",
    "685": "泉州",
    "645": "扬州",
    "646": "镇江",
    "665": "芜湖",
    "721": "洛阳",
    "740": "襄阳",
    "739": "宜昌",
}

THEMUSE_LOCATIONS = [
    "Remote",
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "Austin, TX",
    "Boston, MA",
    "Chicago, IL",
    "Los Angeles, CA",
    "Washington, DC",
    "Atlanta, GA",
    "Dallas, TX",
    "Denver, CO",
    "Toronto, Canada",
    "Vancouver, Canada",
    "London, United Kingdom",
    "Berlin, Germany",
    "Paris, France",
    "Amsterdam, Netherlands",
    "Dublin, Ireland",
    "Singapore",
    "Bengaluru, India",
    "Hyderabad, India",
    "Tokyo, Japan",
    "Sydney, Australia",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=3000)
    parser.add_argument("--max-pages-per-query-city", type=int, default=30)
    parser.add_argument("--recent-since", default="2024-07-06")
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--skip-zhaopin", action="store_true")
    parser.add_argument("--skip-national", action="store_true")
    parser.add_argument("--expand-citymap", action="store_true")
    parser.add_argument("--start-page", type=int, default=1)
    args = parser.parse_args()

    helper = load_helper()
    helper.FETCH_ROOT.mkdir(parents=True, exist_ok=True)
    search_cities = SEARCH_CITIES
    if args.expand_citymap:
        if args.cache_only:
            search_cities = {**SEARCH_CITIES, **discover_cached_city_codes()}
        else:
            search_cities = {**SEARCH_CITIES, **fetch_zhaopin_citymap_cities()}
    cutoff = helper.parse_date(args.recent_since)
    scrape_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    existing_rows = helper.read_jsonl(JD_JSONL) if JD_JSONL.exists() else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {
        "existing_before": len(existing_rows),
        "existing_kept": 0,
        "existing_rejected": 0,
        "pages_attempted": 0,
        "pages_parsed": 0,
        "pages_failed": 0,
        "positions_seen": 0,
        "duplicate_skipped": 0,
        "missing_id_skipped": 0,
        "old_skipped": 0,
        "weak_skipped": 0,
        "foreign_skipped": 0,
        "workers": max(1, args.workers),
    }

    for row in existing_rows:
        job_id = row.get("job_id")
        if job_id is None:
            stats["existing_rejected"] += 1
            continue
        if row.get("source_name") != "zhaopin":
            stats["existing_rejected"] += 1
            stats["foreign_skipped"] += 1
            continue
        key = str(job_id)
        if key in seen:
            stats["duplicate_skipped"] += 1
            continue
        if helper.is_recent(str(row.get("publish_date") or ""), cutoff) and is_strong_ai_ml_related(row):
            rows.append(row)
            seen.add(key)
            stats["existing_kept"] += 1
            if len(rows) >= args.target_total:
                break
        else:
            stats["existing_rejected"] += 1

    used_tasks: list[dict[str, Any]] = []
    if len(rows) < args.target_total and not args.skip_zhaopin:
        progress_checkpoint = 0
        if args.cache_only:
            tasks = iter_cached_tasks(
                search_cities=search_cities,
                start_page=args.start_page,
                max_page=args.max_pages_per_query_city,
                include_national=not args.skip_national,
            )
        else:
            tasks = iter_tasks(
                helper,
                args.max_pages_per_query_city,
                include_national=not args.skip_national,
                search_cities=search_cities,
                start_page=args.start_page,
            )
        batch_size = max(1, args.workers) * 4
        for start in range(0, len(tasks), batch_size):
            if len(rows) >= args.target_total:
                break

            batch = tasks[start : start + batch_size]
            stats["pages_attempted"] += len(batch)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
                future_to_task = {
                    executor.submit(fetch_and_parse_zhaopin, helper, task, args.cache_only): task for task in batch
                }
                for future in concurrent.futures.as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        stats["pages_failed"] += 1
                        print(
                            json.dumps(
                                {
                                    "zhaopin_parse_failed": {
                                        "keyword": task.keyword,
                                        "city": task.city_name,
                                        "page": task.page,
                                        "error": str(exc),
                                    }
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                        continue

                    if not result.get("html"):
                        stats["pages_failed"] += 1
                        continue
                    items = result.get("items") or []
                    if not items:
                        continue

                    stats["pages_parsed"] += 1
                    stats["positions_seen"] += len(items)
                    used_tasks.append(
                        {
                            "keyword": task.keyword,
                            "city": task.city_name,
                            "city_code": task.city_code,
                            "page": task.page,
                        }
                    )

                    for item in items:
                        if len(rows) >= args.target_total:
                            break
                        job_id = item.get("jobId")
                        if job_id is None:
                            stats["missing_id_skipped"] += 1
                            continue
                        key = str(job_id)
                        if key in seen:
                            stats["duplicate_skipped"] += 1
                            continue
                        if quick_reject_zhaopin_item(item):
                            stats["weak_skipped"] += 1
                            continue
                        row = helper.convert_item(item, task, scrape_time)
                        if not helper.is_recent(row["publish_date"], cutoff):
                            stats["old_skipped"] += 1
                            continue
                        if not is_strong_ai_ml_related(row):
                            stats["weak_skipped"] += 1
                            continue
                        rows.append(row)
                        seen.add(key)

            if args.sleep_seconds > 0 and not args.cache_only:
                time.sleep(args.sleep_seconds)

            if stats["pages_attempted"] - progress_checkpoint >= 200 or len(rows) >= args.target_total:
                progress_checkpoint = stats["pages_attempted"]
                print(
                    json.dumps(
                        {
                            "progress": {
                                "total_rows": len(rows),
                                "target_total": args.target_total,
                                "pages_attempted": stats["pages_attempted"],
                                "pages_parsed": stats["pages_parsed"],
                                "positions_seen": stats["positions_seen"],
                            }
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    if len(rows) < args.target_total:
        raise SystemExit(
            json.dumps(
                {
                    "status": "insufficient_domestic_strong_ai_ml_rows",
                    "collected": len(rows),
                    "target_total": args.target_total,
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    rows = rows[: args.target_total]
    rows = sort_rows(rows)
    write_jsonl(JD_JSONL, rows)
    write_csv(JD_CSV, rows, helper.CSV_FIELDS)
    update_summary(
        helper=helper,
        rows=rows,
        stats=stats,
        used_tasks=used_tasks,
        scrape_time=scrape_time,
        recent_since=args.recent_since,
        search_cities=search_cities,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "total_after": len(rows),
                "unique_job_ids": len({str(row.get("job_id")) for row in rows}),
                "first_job_id": rows[0]["job_id"],
                "last_job_id": rows[-1]["job_id"],
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("append_ai_jd_data", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load helper: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def iter_tasks(
    helper: Any,
    max_pages: int,
    *,
    include_national: bool,
    search_cities: dict[str, str],
    start_page: int = 1,
) -> list[Any]:
    tasks = []
    for page in range(max(1, start_page), max_pages + 1):
        for keyword in STRONG_KEYWORDS:
            if include_national:
                tasks.append(NationalFetchTask(keyword=keyword, page=page))
            for city_code, city_name in search_cities.items():
                tasks.append(helper.FetchTask(keyword=keyword, city_code=city_code, city_name=city_name, page=page))
    return tasks


def iter_cached_tasks(
    *,
    search_cities: dict[str, str],
    start_page: int,
    max_page: int,
    include_national: bool,
) -> list[CachedFetchTask]:
    matched: list[tuple[int, str, str, Path]] = []
    for path in FETCH_ROOT.glob("*.html"):
        match = re.match(r"(?P<city>\d+|all)_(?P<keyword>.+)_(?P<page>\d+)\.html$", path.name)
        if not match:
            continue
        city_code = match.group("city")
        if city_code == "all" and not include_national:
            continue
        page = int(match.group("page"))
        if page < max(1, start_page) or page > max_page:
            continue
        matched.append((page, match.group("keyword"), city_code, path))

    tasks: list[CachedFetchTask] = []
    for page, keyword, city_code, path in sorted(matched):
        city_name = "全国" if city_code == "all" else search_cities.get(city_code, city_code)
        tasks.append(
            CachedFetchTask(
                keyword=keyword.replace("_", " "),
                city_code=city_code,
                city_name=city_name,
                page=page,
                cached_path=path,
            )
        )
    return tasks


def fetch_and_parse_zhaopin(helper: Any, task: Any, cache_only: bool) -> dict[str, Any]:
    html_text = fetch_zhaopin_html(task, cache_only=cache_only)
    if not html_text:
        return {"html": False, "items": []}
    return {"html": True, "items": helper.parse_positions(html_text)}


def fetch_zhaopin_html(task: Any, *, cache_only: bool = False) -> str:
    cache_path = task.cache_path
    if cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8", errors="replace")
        if is_usable_zhaopin_html(cached) or cache_only:
            return cached
    if cache_only:
        return ""

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            text = fetch_zhaopin_html_via_powershell(task.url)
            if not is_usable_zhaopin_html(text):
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return ""
            cache_path.write_text(text, encoding="utf-8")
            return text
        except Exception:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return ""
    return ""


def is_usable_zhaopin_html(text: str) -> bool:
    return '"positionList"' in text or "__INITIAL_STATE__" in text


def fetch_zhaopin_html_via_powershell(url: str) -> str:
    ps_command = (
        "$ProgressPreference='SilentlyContinue'; "
        f"$uri='{url}'; "
        "$headers=@{"
        "'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36';"
        "'Accept-Language'='zh-CN,zh;q=0.9';"
        "'Referer'='https://sou.zhaopin.com/'"
        "}; "
        "(Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $headers -TimeoutSec 45).Content"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_command],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return completed.stdout


def fetch_zhaopin_citymap_cities() -> dict[str, str]:
    ps_command = (
        "$ProgressPreference='SilentlyContinue'; "
        "$uri='https://www.zhaopin.com/citymap'; "
        "$headers=@{"
        "'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36';"
        "'Accept-Language'='zh-CN,zh;q=0.9';"
        "'Referer'='https://www.zhaopin.com/'"
        "}; "
        "(Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $headers -TimeoutSec 45).Content"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_command],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    cities: dict[str, str] = {}
    pattern = re.compile(
        r'\{"name":"(?P<name>[^"]+)","url":"(?P<url>//(?:www|jobs)\.zhaopin\.com/[^"]+)",'
        r'"code":"(?P<code>\d+)","pinyin":"[^"]+"'
    )
    excluded = {"香港", "澳门", "台湾"}
    for match in pattern.finditer(completed.stdout):
        name = match.group("name")
        code = match.group("code")
        if name in excluded:
            continue
        cities[code] = name
    return cities


def discover_cached_city_codes() -> dict[str, str]:
    cities: dict[str, str] = {}
    for path in FETCH_ROOT.glob("*.html"):
        match = re.match(r"(?P<city>\d+)_", path.name)
        if not match:
            continue
        code = match.group("city")
        cities[code] = SEARCH_CITIES.get(code, code)
    return cities


def iter_themuse_jobs(categories: list[str], max_pages: int, workers: int, locations: list[str]) -> Any:
    tasks = [
        (category, page, location)
        for category in [item.strip() for item in categories if item.strip()]
        for location in locations
        for page in range(1, max_pages + 1)
    ]
    chunk_size = max(1, workers) * 8
    for start in range(0, len(tasks), chunk_size):
        chunk = tasks[start : start + chunk_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(fetch_themuse_page, task) for task in chunk]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result.get("error"):
                    print(json.dumps({"themuse_fetch_failed": result}, ensure_ascii=False), flush=True)
                    continue
                for job in result.get("jobs") or []:
                    if isinstance(job, dict):
                        yield job, result["page"], result["category"]


def fetch_themuse_page(task: tuple[str, int, str]) -> dict[str, Any]:
    category, page, location = task
    url = f"https://www.themuse.com/api/public/jobs?page={page}&category={quote(category)}"
    if location:
        url += f"&location={quote(location)}"
    for attempt in range(3):
        try:
            payload = json.loads(
                urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 Codex"}), timeout=30).read().decode("utf-8")
            )
            break
        except HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"category": category, "page": page, "location": location, "error": str(exc), "jobs": []}
        except Exception as exc:
            return {"category": category, "page": page, "location": location, "error": str(exc), "jobs": []}
    return {"category": category, "page": page, "location": location, "jobs": payload.get("results") or []}


def convert_themuse_job(job: dict[str, Any], page: int, category: str, scrape_time: str) -> dict[str, Any]:
    tags = tag_names(job.get("tags")) + tag_names(job.get("categories"))
    locations = tag_names(job.get("locations"))
    company = job.get("company") if isinstance(job.get("company"), dict) else {}
    description = normalize_html(job.get("contents"))
    lines = split_lines(description)
    return {
        "source_type": "job_platform",
        "source_name": "themuse",
        "page": page,
        "job_id": f"themuse_{job.get('id')}",
        "job_title": clean(job.get("name")),
        "company_name": clean(company.get("name")),
        "industry": category,
        "location": ", ".join(locations),
        "salary_min": "",
        "salary_max": "",
        "experience": "",
        "education": "",
        "publish_date": clean(job.get("publication_date"))[:10],
        "jd_text": description,
        "responsibilities": lines,
        "requirements": lines,
        "skills_raw": tags,
        "skills_norm": tags,
        "url": ((job.get("refs") or {}).get("landing_page") if isinstance(job.get("refs"), dict) else "") or "",
        "scrape_time": scrape_time,
    }


def tag_names(values: Any) -> list[str]:
    names: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            text = clean(value.get("name") or value.get("short_name"))
        else:
            text = clean(value)
        if text:
            names.append(text)
    return names


def normalize_html(value: Any) -> str:
    text = clean(value)
    text = re.sub(r"</?(?:div|p|br|span|li|ul|ol|h1|h2|h3|h4|strong|em)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"\r?\n+", text) if line.strip()]


def quick_reject_zhaopin_item(item: dict[str, Any]) -> bool:
    title = first_text(item.get("name"), get_path(item, ["jobDetailData", "position", "base", "positionName"]))
    if HARD_WEAK_TITLE_RE.search(title) or NON_DEVELOPMENT_TITLE_RE.search(title):
        return True
    if NONTECH_EVAL_RE.search(title):
        return True

    text = raw_item_text(item, title)
    return not has_ai_development_title(title) or not AI_BUILD_ACTION_RE.search(text)


def raw_item_text(item: dict[str, Any], title: str) -> str:
    pieces = [
        title,
        first_text(item.get("industryName")),
        first_text(item.get("companyName"), get_path(item, ["jobDetailData", "companyProxy", "companyName"])),
        first_text(item.get("jobSummary")),
        first_text(item.get("positionHighlight")),
        first_text(get_path(item, ["jobDetailData", "position", "desc", "description"])),
    ]
    pieces.extend(raw_skill_names(item))
    return " ".join(piece for piece in pieces if piece)


def raw_skill_names(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["jobSkillTags", "skillLabel", "showSkillTags"]:
        for tag in item.get(key) or []:
            if isinstance(tag, dict):
                values.append(first_text(tag.get("name"), tag.get("value"), tag.get("tag"), tag.get("itemValue")))
            else:
                values.append(first_text(tag))
    for tag in get_path(item, ["jobKeyword", "keywords"]) or []:
        values.append(first_text(tag.get("itemValue")) if isinstance(tag, dict) else first_text(tag))
    labels = get_path(item, ["jobDetailData", "position", "desc", "labels"])
    if isinstance(labels, list):
        values.extend(first_text(label) for label in labels)
    return [value for value in values if value]


def get_path(obj: Any, path: list[str]) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_text(*values: Any) -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return ""


def is_themuse_recent(value: str, cutoff: datetime) -> bool:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) >= cutoff
    except ValueError:
        return False


def is_strong_ai_ml_related(row: dict[str, Any]) -> bool:
    title = str(row.get("job_title") or "")
    text = row_text(row)
    body = row_body_text(row)
    if row.get("source_name") != "zhaopin":
        return False
    if HARD_WEAK_TITLE_RE.search(title) or NON_DEVELOPMENT_TITLE_RE.search(title):
        return False
    if NONTECH_EVAL_RE.search(title):
        return False
    if not has_ai_development_title(title):
        return False
    if not AI_BUILD_ACTION_RE.search(body):
        return False

    evidence_count = ai_technical_evidence_count(body)
    if OPENCLAW_RE.search(title):
        return evidence_count >= 2 and bool(OPENCLAW_DEVELOPMENT_RE.search(text))

    if NON_AI_TECH_TITLE_RE.search(title) and evidence_count < 2:
        return False
    if SPECIFIC_AI_TITLE_RE.search(title) or ALGORITHM_TITLE_RE.search(title):
        return evidence_count >= 1

    # A bare "AI" in an otherwise generic engineering title is not enough.
    return bool(DEVELOPMENT_TITLE_RE.search(title)) and evidence_count >= 2


def has_ai_development_title(title: str) -> bool:
    if SPECIFIC_AI_TITLE_RE.search(title) or ALGORITHM_TITLE_RE.search(title):
        return True
    return bool(REQUIRED_TITLE_RE.search(title) and DEVELOPMENT_TITLE_RE.search(title))


def ai_technical_evidence_count(text: str) -> int:
    return sum(1 for evidence_re in AI_TECHNICAL_EVIDENCE_RES if evidence_re.search(text))


def row_text(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("job_title") or ""),
        str(row.get("industry") or ""),
        str(row.get("jd_text") or ""),
        str(row.get("company_name") or ""),
    ]
    for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
        value = row.get(key) or []
        pieces.append(" ".join(map(str, value)) if isinstance(value, list) else str(value))
    return " ".join(pieces)


def row_body_text(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("jd_text") or ""),
        str(row.get("industry") or ""),
        str(row.get("company_name") or ""),
    ]
    for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
        value = row.get(key) or []
        pieces.append(" ".join(map(str, value)) if isinstance(value, list) else str(value))
    return " ".join(pieces)


def core_term_count(text: str) -> int:
    return sum(1 for term in CORE_TERMS if re.search(term_pattern(term), text, re.IGNORECASE))


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("job_title") or "").casefold(),
            str(row.get("company_name") or "").casefold(),
            str(row.get("location") or "").casefold(),
            str(row.get("job_id") or ""),
        ),
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            line = line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
            handle.write(line + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            for key in ["responsibilities", "requirements", "skills_raw", "skills_norm"]:
                output[key] = json.dumps(output[key] if isinstance(output[key], list) else [], ensure_ascii=False)
            writer.writerow(output)


def update_summary(
    *,
    helper: Any,
    rows: list[dict[str, Any]],
    stats: dict[str, int],
    used_tasks: list[dict[str, Any]],
    scrape_time: str,
    recent_since: str,
    search_cities: dict[str, str],
) -> None:
    summary = json.loads(JD_SUMMARY.read_text(encoding="utf-8")) if JD_SUMMARY.exists() else {}
    source_counts: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source_name") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    summary.update(
        {
            "source": "zhaopin",
            "keyword": "domestic strong AI/ML technical jobs only; sorted by job_title",
            "deduped": len({str(row.get("job_id")) for row in rows}),
            "saved": len(rows),
            "output": str(JD_JSONL.resolve()),
            "generated_at": scrape_time,
            "source_counts": source_counts,
        }
    )
    summary["last_append"] = {
        "source": "zhaopin_search_page",
        "topic": "domestic strong AI/ML technical jobs only",
        "keywords": STRONG_KEYWORDS,
        "cities": ["全国", *list(search_cities.values())],
        "fallback_source": None,
        "source_counts": source_counts,
        "recent_since": recent_since,
        "total_after": len(rows),
        "sort": "job_title, company_name, location, job_id",
        "workers": stats.get("workers"),
        "scrape_time": scrape_time,
        "filter": {
            "required_title_terms": REQUIRED_TITLE_TERMS,
            "core_terms": CORE_TERMS,
            "title_strong_terms": TITLE_STRONG_TERMS,
            "weak_title_terms": WEAK_TITLE_TERMS,
            "hard_weak_title_terms": HARD_WEAK_TITLE_TERMS,
            "soft_tech_weak_title_terms": SOFT_TECH_WEAK_TITLE_TERMS,
            "engineering_title_terms": ENGINEERING_TITLE_TERMS,
            "non_development_title_terms": NON_DEVELOPMENT_TITLE_TERMS,
            "specific_ai_title_terms": SPECIFIC_AI_TITLE_TERMS,
            "technical_evidence_groups": AI_TECHNICAL_EVIDENCE_GROUPS,
            "selection_rule": "AI-development title plus technical evidence in JD text",
            "domestic_only": True,
        },
        "stats": stats,
        "used_task_count": len(used_tasks),
        "first_tasks": used_tasks[:20],
        "last_tasks": used_tasks[-20:],
    }
    JD_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
