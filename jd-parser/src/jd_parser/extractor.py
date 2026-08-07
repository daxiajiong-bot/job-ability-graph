from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .cleaner import clean_text
from .schemas import JDConstraints, JDProfile, Skill, SkillLevel, TextConstraint, IntConstraint


class JDExtractor(Protocol):
    def extract(self, document_id: str, raw_text: str) -> JDProfile:
        ...


RESP_HEADINGS = ("岗位职责", "工作职责", "职责描述", "工作内容", "主要职责", "职位描述", "Responsibilities")
REQ_HEADINGS = ("任职要求", "岗位要求", "任职资格", "职位要求", "岗位资格", "任职条件", "Requirements", "Qualifications")
PREF_HEADINGS = ("优先条件", "加分项", "优先考虑", "优先", "Preferred", "Bonus")
STOP_HEADINGS = ("福利待遇", "薪资福利", "公司介绍", "职位福利", "工作时间", "Benefits")
METADATA_PREFIXES = ("岗位名称", "职位名称", "工作地点", "地点", "城市", "工作城市", "学历要求", "经验要求")

REQUIRED_HINTS = ("要求", "必须", "熟练", "熟悉", "精通", "掌握", "具备", "需要", "本科", "硕士", "博士", "经验")
PREFERRED_HINTS = ("优先", "加分", "prefer", "plus")
RESP_HINTS = ("负责", "参与", "承担", "推进", "设计", "开发", "构建", "优化", "维护", "跟踪", "完成")

SKILL_PATTERNS = [
    r"Spring\s*Boot",
    r"Robot\s*Framework",
    r"SQL\s*Server",
    r"PostgreSQL",
    r"TensorFlow",
    r"PyTorch",
    r"Python",
    r"JavaScript",
    r"TypeScript",
    r"Java",
    r"C\+\+",
    r"C#",
    r"\.NET",
    r"Go",
    r"Rust",
    r"Shell",
    r"SQL",
    r"MySQL",
    r"Oracle",
    r"Redis",
    r"MongoDB",
    r"Elasticsearch",
    r"Linux",
    r"Docker",
    r"Kubernetes",
    r"K8s",
    r"Git",
    r"Hadoop",
    r"Spark",
    r"Flink",
    r"Kafka",
    r"OpenCV",
    r"MATLAB",
    r"Matlab",
    r"Simulink",
    r"CUDA",
    r"TensorRT",
    r"ONNX",
    r"ROS",
    r"RAG",
    r"LoRA",
    r"LangChain",
    r"LlamaIndex",
    r"FAISS",
    r"Milvus",
    r"Transformer",
    r"BERT",
    r"GPT",
    r"OCR",
    r"ASR",
    r"TTS",
    r"AIGC",
    r"AI\s*Agent",
    r"Agent",
    r"自然语言处理",
    r"计算机视觉",
    r"知识图谱",
    r"机器学习",
    r"深度学习",
    r"强化学习",
    r"推荐系统",
    r"搜索推荐",
    r"数据挖掘",
    r"数据分析",
    r"算法设计",
    r"算法开发",
    r"控制算法",
    r"模型训练",
    r"模型推理",
    r"模型部署",
    r"模型微调",
    r"微调",
    r"信息抽取",
    r"大语言模型",
    r"大模型",
    r"多模态",
    r"人工智能",
    r"机器视觉",
    r"视觉算法",
    r"图像处理",
    r"图像识别",
    r"目标检测",
    r"语音识别",
    r"语音合成",
    r"文心一言",
    r"通义千问",
    r"模型评估",
    r"特征工程",
    r"系统设计",
    r"架构设计",
    r"性能优化",
    r"嵌入式开发",
    r"数字信号处理",
    r"自动控制",
    r"SolidWorks",
    r"结构设计",
]

DEGREE_PATTERNS = [
    r"博士(?:及以上|以上)?",
    r"硕士(?:及以上|以上)?",
    r"研究生(?:及以上|以上)?",
    r"本科(?:及以上|以上)?",
    r"大专(?:及以上|以上)?",
    r"专科(?:及以上|以上)?",
]

CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass
class SectionedText:
    title: str | None
    responsibilities: list[str]
    requirements: list[str]
    preferred: list[str]
    body_lines: list[tuple[str, str]]


def _compact_item(line: str) -> str:
    return re.sub(r"^\s*[\d一二三四五六七八九十]+[\.、)]\s*", "", line).strip(" -；;")


def _is_heading(line: str, headings: tuple[str, ...]) -> bool:
    normalized = line.strip().strip(":： ")
    return any(normalized.lower() == heading.lower() for heading in headings)


def _split_heading_inline(line: str) -> tuple[str | None, str]:
    for heading in RESP_HEADINGS + REQ_HEADINGS + PREF_HEADINGS + STOP_HEADINGS:
        match = re.match(rf"^\s*{re.escape(heading)}\s*[:：]?\s*(.*)$", line, flags=re.I)
        if match:
            return heading, match.group(1).strip()
    return None, line


def _section_for_heading(heading: str | None) -> str | None:
    if heading is None:
        return None
    if any(heading.lower() == item.lower() for item in RESP_HEADINGS):
        return "responsibilities"
    if any(heading.lower() == item.lower() for item in REQ_HEADINGS):
        return "requirements"
    if any(heading.lower() == item.lower() for item in PREF_HEADINGS):
        return "preferred"
    if any(heading.lower() == item.lower() for item in STOP_HEADINGS):
        return "stop"
    return None


def _first_match(patterns: list[str], text: str) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match
    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _extract_title(lines: list[str]) -> str | None:
    for line in lines[:8]:
        match = re.search(r"^(?:岗位名称|职位名称|岗位|职位)\s*[:：]\s*(.+)$", line)
        if match:
            return match.group(1).strip()
    for line in lines:
        if not line or _section_for_heading(_split_heading_inline(line)[0]):
            continue
        if len(line) <= 80:
            return line.strip()
    return None


def section_text(cleaned_text: str) -> SectionedText:
    lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    title = _extract_title(lines)
    responsibilities: list[str] = []
    requirements: list[str] = []
    preferred: list[str] = []
    body_lines: list[tuple[str, str]] = []
    current: str | None = None

    for line in lines:
        heading, rest = _split_heading_inline(line)
        section = _section_for_heading(heading)
        if section == "stop":
            current = "stop"
            continue
        if section:
            current = section
            if not rest:
                continue
            line = rest
        elif current == "stop":
            continue

        if re.match(rf"^\s*(?:{'|'.join(METADATA_PREFIXES)})\s*[:：]", line, flags=re.I):
            continue

        item = _compact_item(line)
        if not item or item == title:
            continue

        target = current
        if target is None:
            if _contains_any(item, PREFERRED_HINTS):
                target = "preferred"
            elif _contains_any(item, REQUIRED_HINTS):
                target = "requirements"
            elif _contains_any(item, RESP_HINTS):
                target = "responsibilities"

        if target == "responsibilities":
            responsibilities.append(item)
            body_lines.append(("responsibilities", item))
        elif target == "requirements":
            requirements.append(item)
            body_lines.append(("requirements", item))
        elif target == "preferred":
            preferred.append(item)
            body_lines.append(("preferred", item))
        else:
            body_lines.append(("mentioned", item))

    return SectionedText(title, _dedupe_list(responsibilities), _dedupe_list(requirements), _dedupe_list(preferred), body_lines)


def _dedupe_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", "", item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _skill_level(section: str, evidence: str) -> SkillLevel:
    if section == "preferred" or _contains_any(evidence, PREFERRED_HINTS):
        return "preferred"
    if section == "requirements" or _contains_any(evidence, REQUIRED_HINTS):
        return "required"
    return "mentioned"


def _extract_skills(body_lines: list[tuple[str, str]]) -> list[Skill]:
    skills: list[Skill] = []
    seen: set[tuple[str, str, str]] = set()
    combined_pattern = re.compile("|".join(f"({pattern})" for pattern in SKILL_PATTERNS), flags=re.I)
    for section, evidence in body_lines:
        for match in combined_pattern.finditer(evidence):
            name = match.group(0).strip()
            if not name:
                continue
            level = _skill_level(section, evidence)
            key = (name.lower(), level, evidence)
            if key in seen:
                continue
            seen.add(key)
            skills.append(Skill(name=name, level=level, evidence=evidence))
    return skills


def _extract_education(lines: list[str]) -> TextConstraint:
    for line in lines:
        if "学历" not in line and not any(degree[:2] in line for degree in ("博士", "硕士", "本科", "大专", "专科", "研究生")):
            continue
        match = _first_match(DEGREE_PATTERNS, line)
        if match:
            return TextConstraint(value=match.group(0), evidence=line)
    return TextConstraint()


def _chinese_number_to_int(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + CHINESE_NUMBERS.get(value[1], 0)
    if value.endswith("十") and len(value) == 2:
        return CHINESE_NUMBERS.get(value[0], 0) * 10
    if len(value) == 3 and value[1] == "十":
        return CHINESE_NUMBERS.get(value[0], 0) * 10 + CHINESE_NUMBERS.get(value[2], 0)
    return None


def _extract_experience(lines: list[str]) -> IntConstraint:
    patterns = [
        r"(\d+|[一二两三四五六七八九十]+)\s*[-~至到]\s*(\d+|[一二两三四五六七八九十]+)\s*年",
        r"(\d+|[一二两三四五六七八九十]+)\s*年\s*(?:及)?以上",
        r"至少\s*(\d+|[一二两三四五六七八九十]+)\s*年",
        r"(\d+|[一二两三四五六七八九十]+)\s*年以上",
    ]
    for line in lines:
        if "年" not in line:
            continue
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                value = _chinese_number_to_int(match.group(1))
                if value is not None and value >= 0:
                    return IntConstraint(value=value, evidence=line)
    return IntConstraint()


def _extract_location(lines: list[str]) -> TextConstraint:
    for line in lines[:12]:
        match = re.search(r"(?:工作地点|地点|城市|工作城市|Location)\s*[:：]\s*(.+)$", line, flags=re.I)
        if match:
            value = match.group(1).strip(" 。；;")
            if value:
                return TextConstraint(value=value, evidence=line)
    return TextConstraint()


class RuleBasedExtractor:
    """Deterministic extractor used when no model provider is available."""

    def extract(self, document_id: str, raw_text: str) -> JDProfile:
        cleaned = clean_text(raw_text)
        sectioned = section_text(cleaned)
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        constraints = JDConstraints(
            education=_extract_education(lines),
            experience_years=_extract_experience(lines),
            location=_extract_location(lines),
        )
        return JDProfile(
            document_id=document_id,
            document_type="job",
            title=sectioned.title,
            responsibilities=sectioned.responsibilities,
            requirements=sectioned.requirements,
            preferred=sectioned.preferred,
            skills=_extract_skills(sectioned.body_lines),
            constraints=constraints,
            raw_text=raw_text,
        )


class MockExtractor:
    def extract(self, document_id: str, raw_text: str) -> JDProfile:
        return JDProfile(document_id=document_id, document_type="job", raw_text=raw_text)
