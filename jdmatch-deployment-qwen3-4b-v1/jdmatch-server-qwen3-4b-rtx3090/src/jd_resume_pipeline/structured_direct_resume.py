from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from jd_resume_pipeline.direct_resume import numbered_requirements
from jd_resume_pipeline.job_spec_semantics import authoritative_semantics
from jd_resume_pipeline.quality import SLOT_ORDER, shingle_similarity, visible_length


STRUCTURED_SCHEMA_VERSION = "resume_structured_direct_v2"
STRUCTURED_SELECTION_VERSION = "structured_direct_micro_v1"
STRUCTURED_MICRO_V1_JD_IDS = (
    "J00621",
    "J00933",
    "J01108",
    "J01157",
    "J01298",
    "J03067",
    "J03271",
    "J03546",
    "J03603",
    "J03893",
    "J04215",
    "J04881",
    "J06115",
    "J06404",
    "J06765",
    "J06796",
    "J06895",
    "J07014",
    "J07854",
    "J08387",
)
STRUCTURED_MODEL = "qwen-plus"
STRUCTURED_TEMPERATURE = 0.7
STRUCTURED_TOP_P = 0.85
STRUCTURED_MAX_TOKENS = 6000
STRUCTURED_CUSTOM_ID_RE = re.compile(
    r"^resume-structured-direct-(J\d+)-v2(?:-r\d+)?$"
)
STRUCTURED_LABEL_FIELDS = ("relevance", "relation", "label", "is_positive")

ALLOWED_DEGREES = {"大专", "本科", "硕士", "博士"}
ALLOWED_COMPANIES = {
    "某科技企业",
    "某互联网企业",
    "某制造企业",
    "某软件企业",
    "某研究机构",
}
TARGET_MIN_LENGTH = 350
TARGET_MAX_LENGTH = 600
HARD_MIN_LENGTH = 250
HARD_MAX_LENGTH = 900
NEAR_DUPLICATE_THRESHOLD = 0.82

PREFERRED_REQUIREMENT_RE = re.compile(
    r"优先(?!级)|加分|更佳|可放宽|优先考虑|非必须|不是必须|"
    r"nice\s+to\s+have|optional|bonus",
    re.IGNORECASE,
)
SOFT_SKILL_RE = re.compile(
    r"沟通|团队(?:协作|合作|精神)?|责任心|抗压|学习能力|"
    r"积极主动|执行力|表达能力|协调能力|工作态度|敬业|品德|"
    r"热情|自驱|逻辑思维|问题分析与解决能力"
)
HARD_TECH_RE = re.compile(
    r"算法|模型|机器学习|深度学习|大模型|LLM|Agent|RAG|"
    r"计算机视觉|图像|视觉|NLP|自然语言|语音|推荐|搜索|"
    r"机器人|控制|嵌入式|数据|架构|微服务|分布式|数据库|"
    r"Python|Java|Go|C\+\+|C#|JavaScript|TypeScript|"
    r"PyTorch|TensorFlow|OpenCV|Docker|Kubernetes|Linux|"
    r"Spring|React|Vue|SQL|Redis|Kafka|ROS|MATLAB",
    re.IGNORECASE,
)
PROJECT_REQUIREMENT_RE = re.compile(
    r"项目|落地|上线|生产|实战|研发经验|开发经验|架构经验|"
    r"从业经验|工作经验|实践经验"
)
YEAR_REQUIREMENT_RE = re.compile(r"\d+\s*年(?:以上|及以上|经验)?")
EDUCATION_REQUIREMENT_RE = re.compile(
    r"大专|本科|硕士|博士|学历|专业|计算机相关|人工智能相关"
)
TITLE_OR_BENEFIT_RE = re.compile(
    r"^(?:(?:岗位说明|职位描述|福利|薪资|待遇|为什么加入|我们提供)"
    r"\s*[:：].*|(?:任职要求|任职资格|岗位要求|职位要求|必备|非必须|"
    r"岗位说明|职位描述|福利|薪资|待遇|为什么加入|我们提供)"
    r"[\s：:（）()]*)$"
)

DATE_RE = re.compile(r"^(?P<year>20\d{2})-(?P<month>0[1-9]|1[0-2])$")
LABEL_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("positive_sample", re.compile(r"正样本")),
    ("negative_sample", re.compile(r"负样本")),
    ("hard_negative", re.compile(r"硬负样本")),
    ("person_job_match", re.compile(r"人岗匹配|岗位匹配|匹配度")),
    (
        "slot_marker",
        re.compile(
            r"(?<![A-Za-z0-9\u3400-\u9fff])(?:P1|P2|H1)"
            r"(?![A-Za-z0-9\u3400-\u9fff])",
            re.IGNORECASE,
        ),
    ),
    (
        "slot_word",
        re.compile(r"(?<![A-Za-z0-9])slot(?![A-Za-z0-9])", re.IGNORECASE),
    ),
)
H1_ABSENCE_RE = re.compile(
    r"未参与|尚未实践|无相关经验|无经验|缺少|不具备|未接触|不了解"
)
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
CONTACT_RE = re.compile(
    r"(?:姓名|身份证|电话|手机|邮箱|微信|WeChat|QQ)\s*(?:号|ID)?\s*[:：]",
    re.IGNORECASE,
)
REAL_SCHOOL_RE = re.compile(r"(?<!某)([\u4e00-\u9fff]{2,16}(?:大学|学院))")
REAL_COMPANY_RE = re.compile(
    r"(?<!某)([\u4e00-\u9fff]{2,24}(?:有限公司|股份公司|集团公司))"
)


STRUCTURED_SYSTEM_PROMPT = """你是中文技术简历结构化数据合成器。根据输入JD生成三份完全虚构的结构化简历，只输出合法JSON对象，绝不直接生成resume_text。

生成规则：
1. P1/P2满足JD核心必需条件，但只覆盖部分优先项。遇到任选技术时只选择合理的一种或少数组合，不堆砌全部技能。
2. P1/P2必须具有不同职业路径、项目背景和技术组合，不能只是同一简历的改写。
3. H1是同领域相邻候选人，拥有较多通用能力，但所有经历均不得体现输入中h1_omitted_requirement指定的要求。
4. H1的omitted_requirement_ids只能严格填写程序给定的一个R编号，不得自行选择、更换或增加；P1/P2必须填写空数组。
5. H1所有字段只描述候选人做过什么。禁止使用“未参与、尚未实践、无相关经验、无经验、缺少、不具备、未接触、不了解”等缺失说明。
6. school只能严格写“某高校”。company只能从以下匿名机构中选择：某科技企业、某互联网企业、某制造企业、某软件企业、某研究机构。
7. 不出现姓名、电话、邮箱、微信、QQ、真实学校和真实公司。
8. summary建议60–150个中文字符；skills建议8–15项；硬范围为6–18项。
9. work_experiences为1–3段，每段details为2–4条；projects为1–2个，每个details为2–4条。
10. 所有年月使用YYYY-MM；只有工作结束时间可以写“至今”。时间线不得倒置或出现互相矛盾的重叠，工作年限必须符合authoritative_experience_requirement。
11. 不输出resume_text，不输出label、relevance或relation。
12. resumes必须恰好包含P1、P2、H1各一份，并严格使用下列字段结构。

输出结构：
{
  "jd_id": "原样返回",
  "resumes": [
    {
      "slot": "P1",
      "summary": "...",
      "education": {
        "degree": "本科|硕士|博士|大专",
        "major": "...",
        "school": "某高校",
        "start": "YYYY-MM",
        "end": "YYYY-MM"
      },
      "skills": ["..."],
      "work_experiences": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM|至今",
          "company": "某科技企业",
          "role": "...",
          "details": ["...", "..."]
        }
      ],
      "projects": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM",
          "name": "某项目",
          "role": "...",
          "technologies": ["..."],
          "details": ["...", "..."]
        }
      ],
      "omitted_requirement_ids": []
    },
    {
      "slot": "P2",
      "summary": "...",
      "education": {
        "degree": "本科|硕士|博士|大专",
        "major": "...",
        "school": "某高校",
        "start": "YYYY-MM",
        "end": "YYYY-MM"
      },
      "skills": ["..."],
      "work_experiences": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM|至今",
          "company": "某科技企业",
          "role": "...",
          "details": ["...", "..."]
        }
      ],
      "projects": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM",
          "name": "某项目",
          "role": "...",
          "technologies": ["..."],
          "details": ["...", "..."]
        }
      ],
      "omitted_requirement_ids": []
    },
    {
      "slot": "H1",
      "summary": "...",
      "education": {
        "degree": "本科|硕士|博士|大专",
        "major": "...",
        "school": "某高校",
        "start": "YYYY-MM",
        "end": "YYYY-MM"
      },
      "skills": ["..."],
      "work_experiences": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM|至今",
          "company": "某科技企业",
          "role": "...",
          "details": ["...", "..."]
        }
      ],
      "projects": [
        {
          "start": "YYYY-MM",
          "end": "YYYY-MM",
          "name": "某项目",
          "role": "...",
          "technologies": ["..."],
          "details": ["...", "..."]
        }
      ],
      "omitted_requirement_ids": ["程序指定的R编号"]
    }
  ]
}"""


@dataclass(frozen=True)
class PreparedStructuredInput:
    payload: dict[str, Any]
    requirement_source: str
    hard_requirement: dict[str, str]


@dataclass
class StructuredParseFailure:
    custom_id: str
    jd_id: str | None
    reason: str


@dataclass
class StructuredParseResult:
    resumes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    failures: list[StructuredParseFailure] = field(default_factory=list)
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    ignored_model_label_fields: int = 0
    ignored_unexpected_rows: int = 0
    api_successful_rows: int = 0
    strict_valid_rows: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    valid_usage: dict[str, int] = field(default_factory=dict)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _hard_requirement_score(requirement: dict[str, str]) -> tuple[int, int]:
    text = _text(requirement.get("text"))
    if (
        len(re.sub(r"\W", "", text)) < 6
        or PREFERRED_REQUIREMENT_RE.search(text)
        or TITLE_OR_BENEFIT_RE.fullmatch(text)
    ):
        return (-1, 0)
    has_tech = bool(HARD_TECH_RE.search(text))
    has_project = bool(PROJECT_REQUIREMENT_RE.search(text))
    has_year = bool(YEAR_REQUIREMENT_RE.search(text))
    has_education = bool(EDUCATION_REQUIREMENT_RE.search(text))
    if SOFT_SKILL_RE.search(text) and not (
        has_tech or has_project or has_year or has_education
    ):
        return (-1, 0)
    if has_tech:
        category = 5
    elif has_project:
        category = 4
    elif has_year:
        category = 3
    elif has_education:
        category = 2
    else:
        return (-1, 0)
    specificity = min(len(text), 200)
    if re.search(r"精通|熟练|掌握|具备|必须|要求|至少", text):
        specificity += 20
    return category, specificity


def select_hard_requirement(
    requirements: Iterable[dict[str, str]],
) -> dict[str, str] | None:
    """Select exactly one reliable H1 omission target deterministically."""

    ranked: list[tuple[int, int, int, dict[str, str]]] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            continue
        requirement_id = _text(requirement.get("id"))
        requirement_text = _text(requirement.get("text"))
        if not re.fullmatch(r"R[1-9]\d*", requirement_id) or not requirement_text:
            continue
        category, specificity = _hard_requirement_score(
            {"id": requirement_id, "text": requirement_text}
        )
        if category < 0:
            continue
        ranked.append(
            (
                -category,
                -specificity,
                index,
                {"id": requirement_id, "text": requirement_text},
            )
        )
    return min(ranked)[3] if ranked else None


def prepare_structured_input(record: dict[str, Any]) -> PreparedStructuredInput:
    jd_id = _text(record.get("jd_id"))
    job_title = _text(record.get("job_title"))
    jd_text = _text(record.get("jd_text"))
    if not jd_id:
        raise ValueError("missing_jd_id")
    if not job_title or not jd_text:
        raise ValueError("missing_job_title_or_jd_text")
    requirements, source = numbered_requirements(record)
    if not requirements:
        raise ValueError("no_usable_requirements")
    hard_requirement = select_hard_requirement(requirements)
    if hard_requirement is None:
        raise ValueError("no_reliable_hard_requirement")
    semantics = authoritative_semantics(record)
    payload = {
        "jd_id": jd_id,
        "job_title": job_title,
        "responsibilities": _text_list(record.get("responsibilities")),
        "requirements": requirements,
        "jd_text": jd_text,
        "education": record.get("education"),
        "authoritative_experience_requirement": semantics[
            "experience_requirement"
        ],
        "authoritative_seniority": semantics["seniority"],
        "h1_omitted_requirement": hard_requirement,
    }
    return PreparedStructuredInput(payload, source, hard_requirement)


def structured_resume_request(
    record: dict[str, Any],
) -> tuple[dict[str, Any], PreparedStructuredInput]:
    prepared = prepare_structured_input(record)
    jd_id = prepared.payload["jd_id"]
    request = {
        "custom_id": f"resume-structured-direct-{jd_id}-v2",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": STRUCTURED_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": STRUCTURED_TEMPERATURE,
            "top_p": STRUCTURED_TOP_P,
            "max_tokens": STRUCTURED_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": STRUCTURED_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请根据以下清洗JD生成结构化三简历JSON：\n"
                        + json.dumps(
                            prepared.payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            ],
        },
    }
    return request, prepared


def build_structured_requests(
    records: Iterable[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, PreparedStructuredInput],
]:
    requests: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    prepared_by_id: dict[str, PreparedStructuredInput] = {}
    for record in records:
        jd_id = _text(record.get("jd_id")) or None
        try:
            request, prepared = structured_resume_request(record)
        except ValueError as exc:
            skipped.append({"jd_id": jd_id, "reason": str(exc)})
            continue
        requests.append(request)
        prepared_by_id[prepared.payload["jd_id"]] = prepared
    return requests, skipped, prepared_by_id


def structured_custom_id_jd_id(custom_id: str) -> str | None:
    match = STRUCTURED_CUSTOM_ID_RE.fullmatch(str(custom_id or ""))
    return match.group(1) if match else None


def _request_payload(request: dict[str, Any]) -> dict[str, Any] | None:
    body = request.get("body")
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or len(messages) < 2:
        return None
    message = messages[1]
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or "\n" not in content:
        return None
    try:
        value = json.loads(content.split("\n", 1)[1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def validate_structured_batch_requests(
    requests: Iterable[dict[str, Any]],
) -> list[str]:
    request_list = list(requests)
    errors: list[str] = []
    custom_ids: list[str] = []
    expected_parameters = {
        "model": STRUCTURED_MODEL,
        "enable_thinking": False,
        "response_format": {"type": "json_object"},
        "temperature": STRUCTURED_TEMPERATURE,
        "top_p": STRUCTURED_TOP_P,
        "max_tokens": STRUCTURED_MAX_TOKENS,
    }
    for line_number, request in enumerate(request_list, 1):
        prefix = f"line {line_number}"
        custom_id = request.get("custom_id")
        if not isinstance(custom_id, str) or not STRUCTURED_CUSTOM_ID_RE.fullmatch(
            custom_id
        ):
            errors.append(f"{prefix}: invalid structured custom_id")
        else:
            custom_ids.append(custom_id)
        if request.get("method") != "POST":
            errors.append(f"{prefix}: method must be POST")
        if request.get("url") != "/v1/chat/completions":
            errors.append(f"{prefix}: invalid url")
        body = request.get("body")
        if not isinstance(body, dict):
            errors.append(f"{prefix}: missing body")
            continue
        for key, expected in expected_parameters.items():
            if body.get(key) != expected:
                errors.append(f"{prefix}: invalid {key}")
        messages = body.get("messages")
        is_retry = isinstance(custom_id, str) and bool(
            re.search(r"-r\d+$", custom_id)
        )
        expected_message_count = 3 if is_retry else 2
        if (
            not isinstance(messages, list)
            or len(messages) != expected_message_count
        ):
            errors.append(
                f"{prefix}: invalid message count for "
                + ("retry" if is_retry else "original request")
            )
            continue
        if messages[0] != {
            "role": "system",
            "content": STRUCTURED_SYSTEM_PROMPT,
        }:
            errors.append(f"{prefix}: system prompt mismatch")
        payload = _request_payload(request)
        required_fields = {
            "jd_id",
            "job_title",
            "responsibilities",
            "requirements",
            "jd_text",
            "education",
            "authoritative_experience_requirement",
            "authoritative_seniority",
            "h1_omitted_requirement",
        }
        if payload is None or not required_fields <= set(payload):
            errors.append(f"{prefix}: embedded payload missing fields")
            continue
        expected_jd_id = structured_custom_id_jd_id(str(custom_id or ""))
        if payload.get("jd_id") != expected_jd_id:
            errors.append(f"{prefix}: payload jd_id does not match custom_id")
        requirements = payload.get("requirements")
        expected_ids = (
            [f"R{index}" for index in range(1, len(requirements) + 1)]
            if isinstance(requirements, list)
            else []
        )
        actual_ids = (
            [
                item.get("id") if isinstance(item, dict) else None
                for item in requirements
            ]
            if isinstance(requirements, list)
            else []
        )
        if not expected_ids or actual_ids != expected_ids:
            errors.append(f"{prefix}: requirements numbering is invalid")
        omitted = payload.get("h1_omitted_requirement")
        if (
            not isinstance(omitted, dict)
            or set(omitted) != {"id", "text"}
            or omitted not in requirements
            or select_hard_requirement(requirements) != omitted
        ):
            errors.append(f"{prefix}: invalid program-selected hard requirement")
    duplicates = sorted(
        custom_id
        for custom_id, count in Counter(custom_ids).items()
        if count > 1
    )
    if duplicates:
        errors.append(f"duplicate custom_id values: {duplicates[:5]}")
    return errors


def _serial_atom(value: Any) -> str:
    return _text(value).replace("；", "，").replace(";", "，")


def serialize_structured_resume(resume: dict[str, Any]) -> str:
    """Serialize a validated structured resume with a stable line contract."""

    education = resume["education"]
    major = _serial_atom(education["major"])
    if not major.endswith("专业"):
        major += "专业"
    lines = [
        "教育："
        + "；".join(
            [
                _serial_atom(education["degree"]),
                major,
                _serial_atom(education["school"]),
                f"{education['start']}至{education['end']}",
            ]
        ),
        "技能：" + "；".join(_serial_atom(skill) for skill in resume["skills"]),
        "相关经验：" + _serial_atom(resume["summary"]),
    ]
    for index, experience in enumerate(resume["work_experiences"], 1):
        lines.append(
            f"工作经历{index}："
            + "；".join(
                [
                    f"{experience['start']}至{experience['end']}",
                    _serial_atom(experience["role"]),
                    _serial_atom(experience["company"]),
                    *[
                        _serial_atom(detail)
                        for detail in experience["details"]
                    ],
                ]
            )
        )
    for index, project in enumerate(resume["projects"], 1):
        lines.append(
            f"项目经历{index}："
            + "；".join(
                [
                    f"{project['start']}至{project['end']}",
                    _serial_atom(project["name"]),
                    _serial_atom(project["role"]),
                    "技术："
                    + "、".join(
                        _serial_atom(technology)
                        for technology in project["technologies"]
                    ),
                    *[_serial_atom(detail) for detail in project["details"]],
                ]
            )
        )
    return "\n".join(lines)


def _month_value(value: Any, *, allow_present: bool = False) -> int | None:
    if allow_present and value == "至今":
        today = date.today()
        return today.year * 12 + today.month
    if not isinstance(value, str):
        return None
    match = DATE_RE.fullmatch(value)
    if not match:
        return None
    return int(match.group("year")) * 12 + int(match.group("month"))


def _required_text(
    value: dict[str, Any],
    key: str,
    prefix: str,
    errors: list[str],
) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not _text(item):
        errors.append(f"{prefix}:invalid_{key}")
        return ""
    return item


def _validate_date_range(
    value: dict[str, Any],
    prefix: str,
    errors: list[str],
    *,
    allow_present_end: bool = False,
) -> tuple[int | None, int | None]:
    start_raw = value.get("start")
    end_raw = value.get("end")
    start = _month_value(start_raw)
    end = _month_value(end_raw, allow_present=allow_present_end)
    if start is None:
        errors.append(f"{prefix}:invalid_start_date")
    if end is None:
        errors.append(f"{prefix}:invalid_end_date")
    if start is not None and end is not None and end < start:
        errors.append(f"{prefix}:date_range_reversed")
    today = date.today()
    current = today.year * 12 + today.month
    if start is not None and start > current:
        errors.append(f"{prefix}:future_start_date")
    if end is not None and end > current:
        errors.append(f"{prefix}:future_end_date")
    return start, end


def _validate_education(
    value: Any, prefix: str, errors: list[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}:invalid_education")
        return
    for key in ("degree", "major", "school", "start", "end"):
        _required_text(value, key, f"{prefix}.education", errors)
    if value.get("degree") not in ALLOWED_DEGREES:
        errors.append(f"{prefix}.education:invalid_degree")
    if value.get("school") != "某高校":
        errors.append(f"{prefix}.education:school_not_anonymous")
    _validate_date_range(value, f"{prefix}.education", errors)


def _validate_work_experiences(
    value: Any, prefix: str, errors: list[str]
) -> list[tuple[int, int]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        errors.append(f"{prefix}:work_experiences_count")
        return []
    intervals: list[tuple[int, int]] = []
    raw_starts: list[int] = []
    present_count = 0
    for index, experience in enumerate(value, 1):
        item_prefix = f"{prefix}.work_experiences[{index}]"
        if not isinstance(experience, dict):
            errors.append(f"{item_prefix}:not_object")
            continue
        for key in ("start", "end", "company", "role"):
            _required_text(experience, key, item_prefix, errors)
        if experience.get("company") not in ALLOWED_COMPANIES:
            errors.append(f"{item_prefix}:company_not_allowed")
        details = experience.get("details")
        if (
            not isinstance(details, list)
            or len(details) < 2
            or any(not isinstance(item, str) or not _text(item) for item in details)
        ):
            errors.append(f"{item_prefix}:invalid_details")
        start, end = _validate_date_range(
            experience, item_prefix, errors, allow_present_end=True
        )
        if experience.get("end") == "至今":
            present_count += 1
        if start is not None and end is not None and end >= start:
            intervals.append((start, end))
            raw_starts.append(start)
    if raw_starts != sorted(raw_starts):
        errors.append(f"{prefix}:work_experiences_not_chronological")
    if present_count > 1:
        errors.append(f"{prefix}:multiple_current_jobs")
    sorted_intervals = sorted(intervals)
    for (_, previous_end), (next_start, _) in zip(
        sorted_intervals, sorted_intervals[1:]
    ):
        if next_start <= previous_end:
            errors.append(f"{prefix}:overlapping_work_experiences")
            break
    return intervals


def _validate_projects(value: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 2:
        errors.append(f"{prefix}:projects_count")
        return
    for index, project in enumerate(value, 1):
        item_prefix = f"{prefix}.projects[{index}]"
        if not isinstance(project, dict):
            errors.append(f"{item_prefix}:not_object")
            continue
        for key in ("start", "end", "name", "role"):
            _required_text(project, key, item_prefix, errors)
        technologies = project.get("technologies")
        if (
            not isinstance(technologies, list)
            or not technologies
            or any(
                not isinstance(item, str) or not _text(item)
                for item in technologies
            )
        ):
            errors.append(f"{item_prefix}:invalid_technologies")
        details = project.get("details")
        if (
            not isinstance(details, list)
            or len(details) < 2
            or any(not isinstance(item, str) or not _text(item) for item in details)
        ):
            errors.append(f"{item_prefix}:invalid_details")
        _validate_date_range(project, item_prefix, errors)


def _experience_months(intervals: Iterable[tuple[int, int]]) -> int:
    months: set[int] = set()
    for start, end in intervals:
        months.update(range(start, end + 1))
    return len(months)


def _label_leaks(text: str) -> list[str]:
    return [
        name for name, pattern in LABEL_LEAK_PATTERNS if pattern.search(text)
    ]


def _identity_leaks(text: str) -> list[str]:
    leaks: list[str] = []
    for name, pattern in (
        ("phone", PHONE_RE),
        ("email", EMAIL_RE),
        ("contact", CONTACT_RE),
        ("real_school", REAL_SCHOOL_RE),
        ("real_company", REAL_COMPANY_RE),
    ):
        if pattern.search(text):
            leaks.append(name)
    return leaks


def _validate_resume(
    resume: dict[str, Any],
    slot: str,
    prepared: PreparedStructuredInput,
    errors: list[str],
    metrics: dict[str, Any],
) -> None:
    prefix = slot
    if "resume_text" in resume:
        errors.append(f"{prefix}:model_resume_text_forbidden")
    _required_text(resume, "summary", prefix, errors)
    _validate_education(resume.get("education"), prefix, errors)
    skills = resume.get("skills")
    if (
        not isinstance(skills, list)
        or not 6 <= len(skills) <= 18
        or any(not isinstance(skill, str) or not _text(skill) for skill in skills)
    ):
        errors.append(f"{prefix}:invalid_skills")
    intervals = _validate_work_experiences(
        resume.get("work_experiences"), prefix, errors
    )
    _validate_projects(resume.get("projects"), prefix, errors)
    omitted = resume.get("omitted_requirement_ids")
    expected_id = prepared.hard_requirement["id"]
    if slot in {"P1", "P2"} and omitted != []:
        errors.append(f"{prefix}:omitted_requirement_ids_not_empty")
    if slot == "H1" and omitted != [expected_id]:
        errors.append("H1:omitted_requirement_id_mismatch")

    months = _experience_months(intervals)
    experience = prepared.payload["authoritative_experience_requirement"]
    minimum = experience.get("min_years")
    maximum = experience.get("max_years")
    if isinstance(minimum, int) and months < minimum * 12:
        errors.append(f"{prefix}:experience_below_authoritative_minimum")
    if isinstance(maximum, int) and months > maximum * 12 + 1:
        errors.append(f"{prefix}:experience_above_authoritative_maximum")

    try:
        resume_text = serialize_structured_resume(resume)
    except (KeyError, TypeError):
        return
    length = visible_length(resume_text)
    leaks = _label_leaks(resume_text)
    identities = _identity_leaks(resume_text)
    metrics[slot] = {
        "serialized_length": length,
        "target_length": TARGET_MIN_LENGTH <= length <= TARGET_MAX_LENGTH,
        "work_experience_months": months,
        "label_leaks": leaks,
        "identity_leaks": identities,
    }
    if length < HARD_MIN_LENGTH or length > HARD_MAX_LENGTH:
        errors.append(f"{prefix}:serialized_length_hard_failure")
    if leaks:
        errors.append(f"{prefix}:label_leak:" + ",".join(leaks))
    if identities:
        errors.append(f"{prefix}:identity_or_contact:" + ",".join(identities))
    if slot == "H1" and H1_ABSENCE_RE.search(resume_text):
        errors.append("H1:absence_statement")


def validate_structured_resume_payload(
    value: dict[str, Any],
    prepared: PreparedStructuredInput,
) -> tuple[dict[str, dict[str, Any]], int, list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    ignored_labels = 0
    expected_jd_id = prepared.payload["jd_id"]
    if value.get("jd_id") != expected_jd_id:
        errors.append("jd_id_mismatch")
    resumes = value.get("resumes")
    if not isinstance(resumes, list) or len(resumes) != 3:
        return {}, ignored_labels, errors + ["resumes_not_length_3"], metrics
    by_slot: dict[str, dict[str, Any]] = {}
    for resume in resumes:
        if not isinstance(resume, dict):
            errors.append("resume_not_object")
            continue
        slot = resume.get("slot")
        if slot not in SLOT_ORDER or slot in by_slot:
            errors.append("invalid_or_duplicate_slot")
            continue
        ignored_labels += sum(key in resume for key in STRUCTURED_LABEL_FIELDS)
        by_slot[slot] = resume
        _validate_resume(resume, slot, prepared, errors, metrics)
    if set(by_slot) != set(SLOT_ORDER):
        errors.append("slots_not_exact")
        return by_slot, ignored_labels, sorted(set(errors)), metrics

    serialized = {
        slot: serialize_structured_resume(by_slot[slot]) for slot in SLOT_ORDER
    }
    similarities: dict[str, float] = {}
    for left, right in (("P1", "P2"), ("P1", "H1"), ("P2", "H1")):
        pair = f"{left}_{right}"
        score = shingle_similarity(serialized[left], serialized[right])
        similarities[pair] = round(score, 4)
        if serialized[left] == serialized[right] or score >= NEAR_DUPLICATE_THRESHOLD:
            errors.append(f"{pair}:near_duplicate")
    metrics["pairwise_similarity"] = similarities
    metrics["target_length_pass_count"] = sum(
        bool(metrics.get(slot, {}).get("target_length")) for slot in SLOT_ORDER
    )
    return by_slot, ignored_labels, sorted(set(errors)), metrics


def structured_edges(jd_id: str) -> list[dict[str, Any]]:
    return [
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-P1",
            "relevance": 2,
            "relation": "positive",
        },
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-P2",
            "relevance": 2,
            "relation": "positive",
        },
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-H1",
            "relevance": 0,
            "relation": "hard_negative",
        },
    ]


def _response_body(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("error"):
        raise ValueError(f"api_error:{row['error']}")
    response = row.get("response")
    if not isinstance(response, dict):
        raise ValueError("missing_response")
    status_code = response.get("status_code", 200)
    if not isinstance(status_code, int) or not 200 <= status_code < 300:
        raise ValueError(f"http_status:{status_code}")
    body = response.get("body", response)
    if not isinstance(body, dict):
        raise ValueError("missing_response_body")
    return body


def _response_content(
    row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    body = _response_body(row)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    first = choices[0]
    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
    if finish_reason not in (None, "stop"):
        raise ValueError(f"unexpected_finish_reason:{finish_reason}")
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_response_json:{exc.msg}") from exc
    elif isinstance(content, dict):
        value = content
    else:
        raise ValueError("missing_message_content")
    if not isinstance(value, dict):
        raise ValueError("response_json_not_object")
    usage_value = body.get("usage")
    usage: dict[str, int] = {}
    if isinstance(usage_value, dict):
        prompt = usage_value.get(
            "prompt_tokens", usage_value.get("input_tokens", 0)
        )
        completion = usage_value.get(
            "completion_tokens", usage_value.get("output_tokens", 0)
        )
        total = usage_value.get("total_tokens", (prompt or 0) + (completion or 0))
        for key, token_count in (
            ("prompt_tokens", prompt),
            ("completion_tokens", completion),
            ("total_tokens", total),
        ):
            if (
                isinstance(token_count, int)
                and not isinstance(token_count, bool)
                and token_count >= 0
            ):
                usage[key] = token_count
    return value, usage


def _usage_from_body(body: dict[str, Any]) -> dict[str, int]:
    usage_value = body.get("usage")
    if not isinstance(usage_value, dict):
        return {}
    prompt = usage_value.get("prompt_tokens", usage_value.get("input_tokens", 0))
    completion = usage_value.get(
        "completion_tokens", usage_value.get("output_tokens", 0)
    )
    total = usage_value.get("total_tokens", (prompt or 0) + (completion or 0))
    output: dict[str, int] = {}
    for key, token_count in (
        ("prompt_tokens", prompt),
        ("completion_tokens", completion),
        ("total_tokens", total),
    ):
        if (
            isinstance(token_count, int)
            and not isinstance(token_count, bool)
            and token_count >= 0
        ):
            output[key] = token_count
    return output


def parse_structured_resume_rows(
    result_rows: Iterable[dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
    expected_custom_ids: set[str] | None = None,
) -> StructuredParseResult:
    result = StructuredParseResult()
    seen: set[str] = set()
    successful: set[str] = set()
    usage_total: Counter[str] = Counter()
    valid_usage_total: Counter[str] = Counter()
    prepared_by_id: dict[str, PreparedStructuredInput] = {}
    for jd_id, record in source_records.items():
        try:
            prepared_by_id[jd_id] = prepare_structured_input(record)
        except ValueError:
            continue
    for row in result_rows:
        custom_id = str(row.get("custom_id") or "")
        jd_id = structured_custom_id_jd_id(custom_id)
        if expected_custom_ids is not None and custom_id not in expected_custom_ids:
            result.ignored_unexpected_rows += 1
            continue
        try:
            body = _response_body(row)
        except ValueError:
            pass
        else:
            usage_total.update(_usage_from_body(body))
            result.api_successful_rows += 1
        if not custom_id or custom_id in seen:
            result.failures.append(
                StructuredParseFailure(
                    custom_id, jd_id, "duplicate_or_missing_custom_id"
                )
            )
            continue
        seen.add(custom_id)
        if jd_id is None:
            result.failures.append(
                StructuredParseFailure(custom_id, None, "invalid_custom_id")
            )
            continue
        prepared = prepared_by_id.get(jd_id)
        if prepared is None:
            result.failures.append(
                StructuredParseFailure(
                    custom_id, jd_id, "missing_or_invalid_source_jd"
                )
            )
            continue
        try:
            value, usage = _response_content(row)
            by_slot, ignored, errors, metrics = (
                validate_structured_resume_payload(value, prepared)
            )
            result.ignored_model_label_fields += ignored
            result.quality_metrics[jd_id] = metrics
            if errors:
                raise ValueError(",".join(errors))
            valid_usage_total.update(usage)
            result.strict_valid_rows += 1
            successful.add(custom_id)
            for slot in SLOT_ORDER:
                result.resumes.append(
                    {
                        "resume_id": f"{jd_id}-{slot}",
                        "jd_id": jd_id,
                        "slot": slot,
                        "resume_text": serialize_structured_resume(by_slot[slot]),
                        "omitted_requirement_ids": list(
                            by_slot[slot]["omitted_requirement_ids"]
                        ),
                    }
                )
            result.edges.extend(structured_edges(jd_id))
        except ValueError as exc:
            result.failures.append(
                StructuredParseFailure(custom_id, jd_id, str(exc))
            )
    if expected_custom_ids is not None:
        failed = {failure.custom_id for failure in result.failures}
        for custom_id in sorted(expected_custom_ids - successful - failed):
            result.failures.append(
                StructuredParseFailure(
                    custom_id,
                    structured_custom_id_jd_id(custom_id),
                    "missing_result",
                )
            )
    rank = {slot: index for index, slot in enumerate(SLOT_ORDER)}
    result.resumes.sort(key=lambda item: (item["jd_id"], rank[item["slot"]]))
    result.edges.sort(
        key=lambda item: (
            item["jd_id"],
            rank[item["resume_id"].rsplit("-", 1)[1]],
        )
    )
    result.usage = dict(usage_total)
    result.valid_usage = dict(valid_usage_total)
    return result


def _targeted_retry_rules(reason: str) -> list[str]:
    checks: tuple[tuple[tuple[str, ...], str], ...] = (
        (
            ("invalid_response_json", "response_json_not_object"),
            "只输出一个完整合法JSON对象，不要输出Markdown、代码围栏或解释。",
        ),
        (
            ("slot", "resumes_not_length_3"),
            "resumes必须恰好包含P1、P2、H1各一次。",
        ),
        (
            ("school", "company", "identity_or_contact"),
            "school严格写“某高校”，company只用允许的匿名机构，并删除身份与联系方式。",
        ),
        (
            ("date", "chronological", "overlapping", "experience_"),
            "修正年月、经历顺序和工作年限，使其符合权威经验要求且不重叠。",
        ),
        (
            ("skills", "work_experiences", "projects", "details"),
            "补齐规定字段和数组数量，所有字段保持正确JSON类型。",
        ),
        (
            ("omitted_requirement", "absence_statement"),
            "H1只填写程序指定的遗漏ID，正文只写做过的事情且不写任何缺失说明。",
        ),
        (
            ("label_leak",),
            "删除样本、匹配、slot以及独立P1/P2/H1等训练标签。",
        ),
        (
            ("near_duplicate",),
            "重写职业路径、项目背景和技术组合，使三份简历明显不同。",
        ),
        (
            ("serialized_length",),
            "补充或压缩真实经历细节，使程序序列化后处于250至900字符硬范围。",
        ),
    )
    rules = [
        rule
        for markers, rule in checks
        if any(marker in reason for marker in markers)
    ]
    rules.append(
        "保持原JD事实边界与完整结构；仍只返回结构化JSON，不生成resume_text。"
    )
    return list(dict.fromkeys(rules))


def structured_retry_request(
    request: dict[str, Any],
    *,
    failure_reason: str,
    previous_output: Any,
    attempt: int = 1,
) -> dict[str, Any]:
    value = copy.deepcopy(request)
    base = re.sub(r"-r\d+$", "", str(value.get("custom_id") or ""))
    if structured_custom_id_jd_id(base) is None:
        raise ValueError("invalid structured custom_id")
    payload = _request_payload(value)
    if payload is None:
        raise ValueError("missing original structured payload")
    omitted = payload.get("h1_omitted_requirement")
    if not isinstance(omitted, dict):
        raise ValueError("missing original h1_omitted_requirement")
    value["custom_id"] = f"{base}-r{attempt}"
    previous_text = (
        previous_output
        if isinstance(previous_output, str)
        else json.dumps(
            previous_output,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    rules = _targeted_retry_rules(failure_reason)
    value["body"]["messages"].append(
        {
            "role": "user",
            "content": (
                "上一次结构化输出未通过本地严格校验。保留原始JD与程序指定的"
                "H1遗漏要求，只修正失败项并重新返回完整结构化JSON。\n"
                f"具体失败原因：{failure_reason}\n"
                "针对性修正规则：\n- "
                + "\n- ".join(rules)
                + "\n原始指定的h1_omitted_requirement：\n"
                + json.dumps(
                    omitted, ensure_ascii=False, separators=(",", ":")
                )
                + "\n上一次无效输出：\n"
                + (previous_text or "（无可用输出）")
            ),
        }
    )
    return value


def build_structured_retry_requests(
    original_requests: Iterable[dict[str, Any]],
    failed_jd_ids: set[str],
    *,
    attempt: int = 1,
    failure_contexts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    contexts = failure_contexts or {}
    retries: list[dict[str, Any]] = []
    for request in original_requests:
        custom_id = str(request.get("custom_id") or "")
        jd_id = structured_custom_id_jd_id(custom_id)
        if jd_id not in failed_jd_ids:
            continue
        context = contexts.get(custom_id, contexts.get(str(jd_id), {}))
        retries.append(
            structured_retry_request(
                request,
                failure_reason=str(
                    context.get("failure_reason")
                    or context.get("reason")
                    or "未提供失败原因"
                ),
                previous_output=context.get("previous_output"),
                attempt=attempt,
            )
        )
    return retries


def jd_length_bucket(record: dict[str, Any]) -> str:
    length = visible_length(str(record.get("jd_text") or ""))
    if length < 500:
        return "short"
    if length < 1000:
        return "medium"
    return "long"


TECHNICAL_DIRECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("llm_agent", re.compile(r"大模型|LLM|Agent|RAG|智能体", re.I)),
    ("computer_vision", re.compile(r"视觉|图像|OpenCV|检测|分割|OCR", re.I)),
    ("speech_audio", re.compile(r"语音|音频|ASR|TTS|声学", re.I)),
    ("search_recommendation", re.compile(r"推荐|搜索|召回|排序|广告算法")),
    ("robotics_control", re.compile(r"机器人|控制算法|运动规划|ROS", re.I)),
    ("data_ml", re.compile(r"数据分析|数据挖掘|机器学习|深度学习|预测模型")),
    ("embedded_iot", re.compile(r"嵌入式|单片机|物联网|MCU|FPGA", re.I)),
    ("frontend_mobile", re.compile(r"前端|Android|iOS|React|Vue|Flutter", re.I)),
    ("backend_platform", re.compile(r"后端|服务端|微服务|分布式|平台架构")),
    ("qa_ops", re.compile(r"测试|运维|SRE|DevOps|质量保障", re.I)),
)


def technical_direction(record: dict[str, Any]) -> str:
    text = f"{record.get('job_title', '')}\n{record.get('jd_text', '')}"
    for name, pattern in TECHNICAL_DIRECTION_RULES:
        if pattern.search(text):
            return name
    return str(record.get("job_family_proxy") or "other")


def _selection_tiebreaker(jd_id: str) -> str:
    return hashlib.sha256(
        f"{STRUCTURED_SELECTION_VERSION}:{jd_id}".encode("utf-8")
    ).hexdigest()


def select_structured_micro_pilot(
    records: Iterable[dict[str, Any]], count: int = 20
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Greedily cover family, seniority, length and direction deterministically."""

    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen_clusters: set[str] = set()
    features: dict[str, tuple[str, str, str, str]] = {}
    for record in sorted(records, key=lambda item: _text(item.get("jd_id"))):
        jd_id = _text(record.get("jd_id"))
        if record.get("split") != "train":
            continue
        cluster = _text(record.get("near_dup_cluster_id"))
        if not jd_id or not cluster or cluster in seen_clusters:
            continue
        seen_clusters.add(cluster)
        try:
            prepared = prepare_structured_input(record)
        except ValueError as exc:
            rejected.append({"jd_id": jd_id, "reason": str(exc)})
            continue
        candidates.append(record)
        features[jd_id] = (
            str(record.get("job_family_proxy") or "unknown"),
            str(prepared.payload["authoritative_seniority"]),
            jd_length_bucket(record),
            technical_direction(record),
        )
    if len(candidates) < count:
        raise ValueError(
            f"not_enough_eligible_train_jds:{len(candidates)}<{count}"
        )

    selected: list[dict[str, Any]] = []
    remaining = list(candidates)
    family_counts: Counter[str] = Counter()
    seniority_counts: Counter[str] = Counter()
    length_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    # structured_direct_micro_v1 is a released, downloaded pilot. Pin its
    # roster when that exact version can be reconstructed so later bug fixes
    # in semantic feature extraction cannot silently rewrite historical data.
    candidates_by_id = {
        _text(record.get("jd_id")): record for record in candidates
    }
    if count == len(STRUCTURED_MICRO_V1_JD_IDS) and all(
        jd_id in candidates_by_id for jd_id in STRUCTURED_MICRO_V1_JD_IDS
    ):
        selected = [
            candidates_by_id[jd_id] for jd_id in STRUCTURED_MICRO_V1_JD_IDS
        ]
        for record in selected:
            family, seniority, length, direction = features[
                _text(record.get("jd_id"))
            ]
            family_counts[family] += 1
            seniority_counts[seniority] += 1
            length_counts[length] += 1
            direction_counts[direction] += 1
        remaining = [
            record for record in remaining if record not in selected
        ]
    while len(selected) < count:
        scored: list[tuple[tuple[int, ...], str, dict[str, Any]]] = []
        for record in remaining:
            jd_id = _text(record.get("jd_id"))
            family, seniority, length, direction = features[jd_id]
            score = (
                int(family_counts[family] == 0),
                int(direction_counts[direction] == 0),
                int(seniority_counts[seniority] == 0),
                int(length_counts[length] == 0),
                -family_counts[family],
                -direction_counts[direction],
                -seniority_counts[seniority],
                -length_counts[length],
            )
            scored.append(
                (score, _selection_tiebreaker(_text(record.get("jd_id"))), record)
            )
        _, _, chosen = max(scored, key=lambda item: (item[0], item[1]))
        selected.append(chosen)
        remaining.remove(chosen)
        family, seniority, length, direction = features[
            _text(chosen.get("jd_id"))
        ]
        family_counts[family] += 1
        seniority_counts[seniority] += 1
        length_counts[length] += 1
        direction_counts[direction] += 1
    selected.sort(key=lambda item: _text(item.get("jd_id")))
    metadata = {
        "selection_version": STRUCTURED_SELECTION_VERSION,
        "eligible_candidate_count": len(candidates),
        "rejected_no_hard_requirement_count": sum(
            item["reason"] == "no_reliable_hard_requirement" for item in rejected
        ),
        "rejected_candidate_count": len(rejected),
        "selected_count": len(selected),
        "job_family_distribution": dict(sorted(family_counts.items())),
        "seniority_distribution": dict(sorted(seniority_counts.items())),
        "jd_length_distribution": dict(sorted(length_counts.items())),
        "technical_direction_distribution": dict(
            sorted(direction_counts.items())
        ),
    }
    return selected, metadata
