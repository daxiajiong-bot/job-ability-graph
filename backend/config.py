from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
SAMPLES_DIR = DATA_DIR / "samples"


@dataclass(frozen=True)
class SourceConfig:
    name: str
    source_type: str
    search_url_template: str
    page_param: str
    page_start: int = 1
    page_size: int = 20
    max_pages: int = 5


SOURCES: List[SourceConfig] = [
    SourceConfig(
        name="zhaopin",
        source_type="job_platform",
        search_url_template="https://sou.zhaopin.com/?jl=765&kw={keyword}&kt=3&p={page}",
        page_param="p",
    ),
    SourceConfig(
        name="lagou",
        source_type="job_platform",
        search_url_template="https://www.lagou.com/wn/jobs?kd={keyword}&pn={page}",
        page_param="pn",
    ),
]

SKILL_SYNONYMS: Dict[str, str] = {
    "py": "Python",
    "python3": "Python",
    "python": "Python",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "linux": "Linux",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "rag": "RAG",
    "llm": "LLM",
    "大模型": "LLM",
    "机器学习": "机器学习",
    "深度学习": "深度学习",
    "数据分析": "数据分析",
    "数据挖掘": "数据挖掘",
    "nlp": "NLP",
    "自然语言处理": "NLP",
}

DEFAULT_KEYWORDS = [
    "Python",
    "Java",
    "大数据",
    "机器学习",
    "算法",
    "物联网",
]
