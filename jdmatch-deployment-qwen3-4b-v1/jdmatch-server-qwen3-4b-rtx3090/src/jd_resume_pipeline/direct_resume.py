from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from jd_resume_pipeline.cleaning import normalize_compact
from jd_resume_pipeline.job_spec_semantics import authoritative_semantics
from jd_resume_pipeline.quality import (
    DATE_RANGE_RE,
    SLOT_ORDER,
    ResumeQuality,
    concept_present,
    containment_copy_rate,
    find_identity_leaks,
    find_label_leaks,
    find_negative_label_leaks,
    seniority_experience_error,
    shingle_similarity,
    timeline_errors,
    visible_length,
    work_experience_months,
)


DIRECT_SCHEMA_VERSION = "resume_direct_v1"
DIRECT_CUSTOM_ID_VERSION = "v1"
DIRECT_MODEL = "qwen-plus"
DIRECT_TEMPERATURE = 0.7
DIRECT_TOP_P = 0.85
DIRECT_MAX_TOKENS = 5500
DIRECT_CUSTOM_ID_RE = re.compile(
    r"^resume-direct-(J\d+)-v1(?:-r\d+)?$"
)
DIRECT_LABEL_FIELDS = ("relevance", "relation", "label", "is_positive")
TARGET_MIN_LENGTH = 700
TARGET_MAX_LENGTH = 1100
HARD_MIN_LENGTH = 500
HARD_MAX_LENGTH = 1500
NEAR_DUPLICATE_THRESHOLD = 0.72
DIRECT_SLOT_LEAK_RE = re.compile(
    r"(?<![A-Za-z0-9])slot(?![A-Za-z0-9])", re.IGNORECASE
)
DIRECT_NAME_MARKER_RE = re.compile(r"姓名")
DIRECT_WECHAT_RE = re.compile(r"微信|WeChat", re.IGNORECASE)
DIRECT_QQ_RE = re.compile(r"(?<![A-Za-z0-9])QQ(?![A-Za-z0-9])", re.IGNORECASE)
MEANINGFUL_FIELD_RE = re.compile(r"\S")
NO_REQUIREMENT_VALUE_RE = re.compile(
    r"^(?:经验)?不限|不限经验|无要求|不要求|暂无|未填写|^-$"
)
FALLBACK_REQUIREMENT_CUE_RE = re.compile(
    r"熟悉|掌握|精通|具备|要求|经验|学历|专业|能力|会使用|能够"
)
TECH_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+#.]{1,30}")
TECH_TOKEN_STOPWORDS = {
    "and",
    "or",
    "with",
    "the",
    "to",
    "of",
    "in",
    "for",
    "job",
    "jd",
}


DIRECT_SYSTEM_PROMPT = """你是中文技术简历合成器。根据输入JD生成P1、P2、H1三份完全虚构的中文简历，只输出合法JSON。

规则：
1. P1、P2符合岗位核心必需条件；遇到“Java/Python/Go至少一种”等任选要求时，只选择合理的一种或少数组合，不堆砌全部候选技术。
2. P1和P2采用不同职业路径、项目场景、技术路线和表达方式，不能只是改写；二者满足必需条件，但只覆盖部分优先项，不生成不现实的全能候选人。
3. H1与岗位属于同一技术领域并保留较多通用技能，但自然缺少1至2项决定性要求；在omitted_requirement_ids中填写对应的R编号，正文不得说明自己缺少能力。
4. 每份正文目标700至1100个中文字符，包含职业摘要、技能、教育、工作经历、项目经历和年月。
5. 时间线和总工作年限必须符合authoritative_experience_requirement及authoritative_seniority。
6. 不出现真实姓名、电话、邮箱、微信、QQ、真实学校或真实公司。
7. 正文不出现P1、P2、H1、slot、positive、negative、正样本、负样本、匹配、硬负等标签。
8. 不直接复制JD长句。
9. 模型不得输出或决定训练标签；任何标签均由程序按slot生成。
10. resumes必须恰好包含P1、P2、H1各一份；P1/P2的omitted_requirement_ids必须为空，H1必须填写1至2个输入中存在的R编号。

输出结构严格为：
{"jd_id":"原样返回","resumes":[{"slot":"P1","resume_text":"...","omitted_requirement_ids":[]},{"slot":"P2","resume_text":"...","omitted_requirement_ids":[]},{"slot":"H1","resume_text":"...","omitted_requirement_ids":["R3"]}]}"""


@dataclass(frozen=True)
class PreparedDirectInput:
    payload: dict[str, Any]
    requirement_source: str


@dataclass
class DirectParseFailure:
    custom_id: str
    jd_id: str | None
    reason: str


@dataclass
class DirectResumeParseResult:
    resumes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    failures: list[DirectParseFailure] = field(default_factory=list)
    qualities: dict[str, ResumeQuality] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    valid_usage: dict[str, int] = field(default_factory=dict)
    api_successful_rows: int = 0
    strict_valid_rows: int = 0
    ignored_model_label_fields: int = 0
    ignored_unexpected_rows: int = 0


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


def _normalize_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {}
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get(
        "completion_tokens", usage.get("output_tokens", 0)
    )
    total = usage.get("total_tokens", (prompt or 0) + (completion or 0))
    normalized: dict[str, int] = {}
    for key, value in (
        ("prompt_tokens", prompt),
        ("completion_tokens", completion),
        ("total_tokens", total),
    ):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            normalized[key] = value
    return normalized


def _response_json_content(
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
    if not isinstance(message, dict):
        raise ValueError("missing_message")
    content = message.get("content")
    if isinstance(content, dict):
        value = content
    elif isinstance(content, str):
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_response_json:{exc.msg}") from exc
    else:
        raise ValueError("missing_message_content")
    if not isinstance(value, dict):
        raise ValueError("response_json_not_object")
    return value, _normalize_usage(body.get("usage", {}))


def _add_usage(total: Counter[str], usage: dict[str, int]) -> None:
    total.update(usage)


def direct_error_reasons(
    rows: Iterable[dict[str, Any]],
) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in rows:
        custom_id = str(row.get("custom_id") or "")
        error = row.get("error")
        output[custom_id] = (
            json.dumps(error, ensure_ascii=False, separators=(",", ":"))
            if error is not None
            else "batch_error"
        )
    return output


def direct_previous_output_from_row(row: dict[str, Any]) -> Any:
    try:
        body = _response_body(row)
    except ValueError:
        return row.get("error")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return body
    first = choices[0]
    if not isinstance(first, dict):
        return first
    message = first.get("message")
    if not isinstance(message, dict):
        return first
    return message.get("content")


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        text
        for item in value
        if (text := re.sub(r"\s+", " ", str(item or "")).strip())
    ]


def _meaningful_structured_value(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not MEANINGFUL_FIELD_RE.search(text) or NO_REQUIREMENT_VALUE_RE.search(text):
        return None
    return text


def numbered_requirements(
    record: dict[str, Any],
) -> tuple[list[dict[str, str]], str]:
    """Number cleaned requirements without reordering or inventing content.

    Empty cleaned arrays use only requirement-like unclassified clauses and
    explicit structured education/experience metadata. Responsibilities remain
    a separate payload field and are never relabeled as requirements.
    """

    requirements = _clean_text_list(record.get("requirements"))
    source = "cleaned_requirements"
    if not requirements:
        fallback: list[str] = []
        for item in _clean_text_list(record.get("unclassified")):
            if FALLBACK_REQUIREMENT_CUE_RE.search(item):
                fallback.append(item)
        education = _meaningful_structured_value(record.get("education"))
        experience = _meaningful_structured_value(record.get("experience"))
        if education:
            fallback.append(f"学历要求（结构化字段）：{education}")
        if experience:
            fallback.append(f"工作经验要求（结构化字段）：{experience}")
        requirements = list(dict.fromkeys(fallback))
        source = "structured_fallback"
    return (
        [
            {"id": f"R{index}", "text": text}
            for index, text in enumerate(requirements, 1)
        ],
        source,
    )


def prepare_direct_input(record: dict[str, Any]) -> PreparedDirectInput:
    jd_id = str(record.get("jd_id") or "").strip()
    if not jd_id:
        raise ValueError("missing_jd_id")
    job_title = str(record.get("job_title") or "").strip()
    jd_text = str(record.get("jd_text") or "").strip()
    if not job_title or not jd_text:
        raise ValueError("missing_job_title_or_jd_text")
    requirements, source = numbered_requirements(record)
    if not requirements:
        raise ValueError("no_usable_requirements")
    semantics = authoritative_semantics(record)
    return PreparedDirectInput(
        payload={
            "jd_id": jd_id,
            "job_title": job_title,
            "responsibilities": _clean_text_list(record.get("responsibilities")),
            "requirements": requirements,
            "jd_text": jd_text,
            "education": record.get("education"),
            "authoritative_experience_requirement": semantics[
                "experience_requirement"
            ],
            "authoritative_seniority": semantics["seniority"],
        },
        requirement_source=source,
    )


def direct_resume_request(
    record: dict[str, Any],
) -> tuple[dict[str, Any], PreparedDirectInput]:
    prepared = prepare_direct_input(record)
    payload = prepared.payload
    request = {
        "custom_id": (
            f"resume-direct-{payload['jd_id']}-{DIRECT_CUSTOM_ID_VERSION}"
        ),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": DIRECT_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": DIRECT_TEMPERATURE,
            "top_p": DIRECT_TOP_P,
            "max_tokens": DIRECT_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请直接根据以下清洗后的JD生成三份简历JSON：\n"
                        + json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            ],
        },
    }
    return request, prepared


def build_direct_requests(
    records: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, PreparedDirectInput]]:
    requests: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    prepared_by_id: dict[str, PreparedDirectInput] = {}
    for record in records:
        jd_id = str(record.get("jd_id") or "").strip() or None
        try:
            request, prepared = direct_resume_request(record)
        except ValueError as exc:
            skipped.append({"jd_id": jd_id, "reason": str(exc)})
            continue
        requests.append(request)
        prepared_by_id[prepared.payload["jd_id"]] = prepared
    return requests, skipped, prepared_by_id


def validate_direct_batch_requests(
    requests: Iterable[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    custom_ids: list[str] = []
    for line_number, request in enumerate(requests, 1):
        prefix = f"line {line_number}"
        custom_id = request.get("custom_id")
        if not isinstance(custom_id, str) or not DIRECT_CUSTOM_ID_RE.fullmatch(
            custom_id
        ):
            errors.append(f"{prefix}: invalid direct custom_id")
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
        expected_parameters = {
            "model": DIRECT_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": DIRECT_TEMPERATURE,
            "top_p": DIRECT_TOP_P,
            "max_tokens": DIRECT_MAX_TOKENS,
        }
        for key, expected in expected_parameters.items():
            if body.get(key) != expected:
                errors.append(f"{prefix}: invalid {key}")
        messages = body.get("messages")
        if not isinstance(messages, list) or len(messages) != 2:
            errors.append(f"{prefix}: messages must contain system and user")
            continue
        if messages[0] != {"role": "system", "content": DIRECT_SYSTEM_PROMPT}:
            errors.append(f"{prefix}: system prompt mismatch")
        user_content = messages[1].get("content") if isinstance(messages[1], dict) else None
        if not isinstance(user_content, str) or "\n" not in user_content:
            errors.append(f"{prefix}: invalid user message")
            continue
        try:
            payload = json.loads(user_content.split("\n", 1)[1])
        except json.JSONDecodeError:
            errors.append(f"{prefix}: embedded payload is invalid JSON")
            continue
        required_fields = {
            "jd_id",
            "job_title",
            "responsibilities",
            "requirements",
            "jd_text",
            "education",
            "authoritative_experience_requirement",
            "authoritative_seniority",
        }
        if not isinstance(payload, dict) or not required_fields <= set(payload):
            errors.append(f"{prefix}: embedded payload missing fields")
            continue
        requirements = payload.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            errors.append(f"{prefix}: embedded requirements are empty")
        else:
            expected_ids = [f"R{index}" for index in range(1, len(requirements) + 1)]
            actual_ids = [
                item.get("id") if isinstance(item, dict) else None
                for item in requirements
            ]
            if actual_ids != expected_ids or any(
                not isinstance(item, dict)
                or not isinstance(item.get("text"), str)
                or not item["text"].strip()
                for item in requirements
            ):
                errors.append(f"{prefix}: requirements numbering is invalid")
        expected_jd_id = direct_custom_id_jd_id(str(custom_id or ""))
        if payload.get("jd_id") != expected_jd_id:
            errors.append(f"{prefix}: payload jd_id does not match custom_id")
    duplicates = sorted(
        value for value, count in Counter(custom_ids).items() if count > 1
    )
    if duplicates:
        errors.append(f"duplicate custom_id values: {duplicates[:5]}")
    return errors


def direct_custom_id_jd_id(custom_id: str) -> str | None:
    match = DIRECT_CUSTOM_ID_RE.fullmatch(str(custom_id or ""))
    return match.group(1) if match else None


def direct_edges(jd_id: str) -> list[dict[str, Any]]:
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


def validate_direct_resume_payload(
    value: dict[str, Any],
    expected_jd_id: str,
    valid_requirement_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], int, list[str]]:
    errors: list[str] = []
    ignored_labels = 0
    if value.get("jd_id") != expected_jd_id:
        errors.append("jd_id_mismatch")
    resumes = value.get("resumes")
    if not isinstance(resumes, list) or len(resumes) != 3:
        return {}, ignored_labels, errors + ["resumes_not_length_3"]
    by_slot: dict[str, dict[str, Any]] = {}
    for resume in resumes:
        if not isinstance(resume, dict):
            errors.append("resume_not_object")
            continue
        slot = resume.get("slot")
        if slot not in SLOT_ORDER or slot in by_slot:
            errors.append("invalid_or_duplicate_slot")
            continue
        ignored_labels += sum(key in resume for key in DIRECT_LABEL_FIELDS)
        if not isinstance(resume.get("resume_text"), str):
            errors.append(f"{slot}:invalid_resume_text")
        omitted = resume.get("omitted_requirement_ids")
        if slot in {"P1", "P2"}:
            if omitted != []:
                errors.append(f"{slot}:omitted_requirement_ids_not_empty")
        elif (
            not isinstance(omitted, list)
            or not 1 <= len(omitted) <= 2
            or not all(isinstance(item, str) for item in omitted)
        ):
            errors.append("H1:missing_or_invalid_omitted_requirement_ids")
        else:
            if len(set(omitted)) != len(omitted):
                errors.append("H1:duplicate_omitted_requirement_ids")
            invalid = sorted(set(omitted) - valid_requirement_ids)
            if invalid:
                errors.append(
                    "H1:unknown_omitted_requirement_ids:" + ",".join(invalid)
                )
        by_slot[slot] = resume
    if set(by_slot) != set(SLOT_ORDER):
        errors.append("slots_not_exact")
    return by_slot, ignored_labels, errors


def _future_date_errors(text: str) -> list[str]:
    current_month = date.today().year * 12 + date.today().month
    errors: list[str] = []
    for match in DATE_RANGE_RE.finditer(text):
        start = int(match.group("sy")) * 12 + int(match.group("sm"))
        if start > current_month:
            errors.append(match.group(0))
        if not match.group("present"):
            end = int(match.group("ey")) * 12 + int(match.group("em"))
            if end > current_month:
                errors.append(match.group(0))
    return errors


def _direct_label_leaks(text: str) -> list[str]:
    leaks = find_label_leaks(text)
    if DIRECT_SLOT_LEAK_RE.search(text):
        leaks.append("slot")
    return sorted(set(leaks))


def _direct_identity_leaks(text: str) -> list[str]:
    leaks = find_identity_leaks(text)
    if DIRECT_NAME_MARKER_RE.search(text):
        leaks.append("name_marker")
    if DIRECT_WECHAT_RE.search(text):
        leaks.append("wechat")
    if DIRECT_QQ_RE.search(text):
        leaks.append("qq")
    return sorted(set(leaks))


def _source_technical_terms(prepared: PreparedDirectInput) -> list[str]:
    payload = prepared.payload
    sources = [
        payload["job_title"],
        payload["jd_text"],
        *payload["responsibilities"],
        *(item["text"] for item in payload["requirements"]),
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for match in TECH_TOKEN_RE.finditer(str(source)):
            term = match.group(0)
            key = term.casefold()
            if key in TECH_TOKEN_STOPWORDS or key in seen:
                continue
            seen.add(key)
            terms.append(term)
    return terms


def _terms_present(terms: Iterable[str], text: str) -> set[str]:
    normalized = normalize_compact(text)
    return {
        term
        for term in terms
        if normalize_compact(term) in normalized
    }


def _section_scope(text: str, heading: str, later_headings: tuple[str, ...]) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    scope = text[start + len(heading) :]
    ends = [
        position
        for later in later_headings
        if (position := scope.find(later)) >= 0
    ]
    return scope[: min(ends)] if ends else scope


def evaluate_direct_triplet(
    resumes_by_slot: dict[str, dict[str, Any]],
    prepared: PreparedDirectInput,
) -> ResumeQuality:
    failures: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {"slots": {}}
    if set(resumes_by_slot) != set(SLOT_ORDER):
        return ResumeQuality(False, ["slots_not_exact"], metrics=metrics)

    payload = prepared.payload
    experience = payload["authoritative_experience_requirement"]
    minimum_years = experience.get("min_years")
    maximum_years = experience.get("max_years")
    seniority = str(payload.get("authoritative_seniority") or "unspecified")
    requirement_texts = {
        item["id"]: item["text"] for item in payload["requirements"]
    }
    source_terms = _source_technical_terms(prepared)
    present_terms: dict[str, set[str]] = {}

    for slot in SLOT_ORDER:
        resume = resumes_by_slot[slot]
        text = resume.get("resume_text")
        if not isinstance(text, str) or not text.strip():
            failures.append(f"{slot}:missing_resume_text")
            continue
        length = visible_length(text)
        label_leaks = _direct_label_leaks(text)
        identity_leaks = _direct_identity_leaks(text)
        timeline = sorted(set(timeline_errors(text) + _future_date_errors(text)))
        experience_months = work_experience_months(text)
        copy_rate = containment_copy_rate(payload["jd_text"], text)
        covered_ids = [
            requirement_id
            for requirement_id, requirement_text in requirement_texts.items()
            if concept_present(requirement_text, text)
        ]
        present_terms[slot] = _terms_present(source_terms, text)
        sections = {
            heading: heading in text
            for heading in (
                "职业摘要",
                "技能",
                "教育",
                "工作经历",
                "项目经历",
            )
        }
        metrics["slots"][slot] = {
            "length": length,
            "within_target_length": TARGET_MIN_LENGTH
            <= length
            <= TARGET_MAX_LENGTH,
            "label_leaks": label_leaks,
            "identity_leaks": identity_leaks,
            "timeline_errors": timeline,
            "work_experience_months": experience_months,
            "jd_copy_rate": round(copy_rate, 4),
            "covered_requirement_ids": covered_ids,
            "requirement_coverage": round(
                len(covered_ids) / max(1, len(requirement_texts)), 4
            ),
            "source_technical_terms_present": sorted(present_terms[slot]),
            "sections_present": sections,
        }
        if not HARD_MIN_LENGTH <= length <= HARD_MAX_LENGTH:
            failures.append(f"{slot}:length")
        elif not TARGET_MIN_LENGTH <= length <= TARGET_MAX_LENGTH:
            warnings.append(f"{slot}:outside_target_length")
        if label_leaks:
            failures.append(f"{slot}:label_leak")
        if identity_leaks:
            failures.append(f"{slot}:identity_or_contact")
        if timeline:
            failures.append(f"{slot}:timeline")
        if isinstance(minimum_years, int) and (
            experience_months is None
            or experience_months < minimum_years * 12
        ):
            failures.append(f"{slot}:experience_minimum")
        if isinstance(maximum_years, int) and (
            experience_months is None
            or experience_months > maximum_years * 12 + 11
        ):
            failures.append(f"{slot}:experience_maximum")
        if seniority_experience_error(seniority, experience_months):
            failures.append(f"{slot}:seniority_experience")
        if copy_rate > 0.25:
            warnings.append(f"{slot}:high_jd_copy_rate")
        if not all(sections.values()):
            warnings.append(f"{slot}:missing_expected_section")
        if slot == "H1":
            negative_leaks = find_negative_label_leaks(text)
            metrics["slots"][slot]["negative_label_leaks"] = negative_leaks
            if negative_leaks:
                failures.append("H1:negative_label_leak")

    texts = {
        slot: str(resumes_by_slot[slot].get("resume_text") or "")
        for slot in SLOT_ORDER
    }
    pairwise_similarity: dict[str, float] = {}
    project_similarity: dict[str, float] = {}
    career_similarity: dict[str, float] = {}
    for left, right in (("P1", "P2"), ("P1", "H1"), ("P2", "H1")):
        pair = f"{left}_{right}"
        similarity = shingle_similarity(texts[left], texts[right])
        pairwise_similarity[pair] = round(similarity, 4)
        if similarity >= NEAR_DUPLICATE_THRESHOLD:
            failures.append(f"{pair}:near_duplicate")
        left_project = _section_scope(
            texts[left], "项目经历", ("教育经历", "工作经历")
        )
        right_project = _section_scope(
            texts[right], "项目经历", ("教育经历", "工作经历")
        )
        project_similarity[pair] = round(
            shingle_similarity(left_project, right_project), 4
        )
        left_work = _section_scope(
            texts[left], "工作经历", ("项目经历", "教育经历")
        )
        right_work = _section_scope(
            texts[right], "工作经历", ("项目经历", "教育经历")
        )
        career_similarity[pair] = round(
            shingle_similarity(left_work, right_work), 4
        )
    metrics["pairwise_text_similarity"] = pairwise_similarity
    metrics["p1_p2_similarity"] = pairwise_similarity["P1_P2"]
    metrics["pairwise_project_similarity"] = project_similarity
    metrics["pairwise_career_path_similarity"] = career_similarity

    positive_terms = present_terms.get("P1", set()) | present_terms.get("P2", set())
    h1_terms = present_terms.get("H1", set())
    metrics["h1_common_skill_overlap"] = round(
        len(positive_terms & h1_terms) / max(1, len(positive_terms)), 4
    )
    metrics["measurable_source_technical_terms"] = source_terms
    if not source_terms:
        warnings.append("technical_skill_overlap_not_measurable")

    omitted_ids = resumes_by_slot["H1"].get("omitted_requirement_ids")
    if isinstance(omitted_ids, list):
        metrics["h1_omitted_requirement_ids"] = omitted_ids
        metrics["h1_omitted_requirements_detected_in_text"] = [
            requirement_id
            for requirement_id in omitted_ids
            if requirement_id in requirement_texts
            and concept_present(requirement_texts[requirement_id], texts["H1"])
        ]
    return ResumeQuality(
        not failures,
        sorted(set(failures)),
        sorted(set(warnings)),
        metrics,
    )


def parse_direct_resume_rows(
    result_rows: Iterable[dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
    expected_custom_ids: set[str] | None = None,
    api_error_reasons: dict[str, str] | None = None,
) -> DirectResumeParseResult:
    result = DirectResumeParseResult()
    actual_usage_total: Counter[str] = Counter()
    valid_usage_total: Counter[str] = Counter()
    seen_custom_ids: set[str] = set()
    successful_custom_ids: set[str] = set()
    api_error_reasons = api_error_reasons or {}

    prepared_by_id: dict[str, PreparedDirectInput] = {}
    for jd_id, record in source_records.items():
        try:
            prepared_by_id[jd_id] = prepare_direct_input(record)
        except ValueError:
            continue

    for row in result_rows:
        custom_id = str(row.get("custom_id") or "")
        jd_id = direct_custom_id_jd_id(custom_id)
        if expected_custom_ids is not None and custom_id not in expected_custom_ids:
            result.ignored_unexpected_rows += 1
            continue
        try:
            body = _response_body(row)
        except ValueError:
            pass
        else:
            _add_usage(
                actual_usage_total, _normalize_usage(body.get("usage", {}))
            )
            result.api_successful_rows += 1
        if not custom_id or custom_id in seen_custom_ids:
            result.failures.append(
                DirectParseFailure(
                    custom_id, jd_id, "duplicate_or_missing_custom_id"
                )
            )
            continue
        seen_custom_ids.add(custom_id)
        if jd_id is None:
            result.failures.append(
                DirectParseFailure(custom_id, None, "invalid_custom_id")
            )
            continue
        prepared = prepared_by_id.get(jd_id)
        if prepared is None:
            result.failures.append(
                DirectParseFailure(custom_id, jd_id, "missing_or_invalid_source_jd")
            )
            continue
        valid_requirement_ids = {
            item["id"] for item in prepared.payload["requirements"]
        }
        try:
            value, usage = _response_json_content(row)
            by_slot, ignored_labels, errors = validate_direct_resume_payload(
                value, jd_id, valid_requirement_ids
            )
            result.ignored_model_label_fields += ignored_labels
            if errors:
                raise ValueError(",".join(errors))
            quality = evaluate_direct_triplet(by_slot, prepared)
            result.qualities[jd_id] = quality
            if not quality.passed:
                raise ValueError("quality:" + ",".join(quality.failures))
            _add_usage(valid_usage_total, usage)
            result.strict_valid_rows += 1
            successful_custom_ids.add(custom_id)
            for slot in SLOT_ORDER:
                result.resumes.append(
                    {
                        "resume_id": f"{jd_id}-{slot}",
                        "jd_id": jd_id,
                        "slot": slot,
                        "resume_text": by_slot[slot]["resume_text"].strip(),
                        "omitted_requirement_ids": list(
                            by_slot[slot]["omitted_requirement_ids"]
                        ),
                    }
                )
            result.edges.extend(direct_edges(jd_id))
        except ValueError as exc:
            result.failures.append(
                DirectParseFailure(custom_id, jd_id, str(exc))
            )

    if expected_custom_ids is not None:
        failed_ids = {failure.custom_id for failure in result.failures}
        missing = (
            expected_custom_ids - successful_custom_ids - failed_ids
        )
        for custom_id in sorted(missing):
            result.failures.append(
                DirectParseFailure(
                    custom_id,
                    direct_custom_id_jd_id(custom_id),
                    api_error_reasons.get(custom_id, "missing_result"),
                )
            )
    slot_rank = {slot: index for index, slot in enumerate(SLOT_ORDER)}
    result.resumes.sort(
        key=lambda item: (item["jd_id"], slot_rank[item["slot"]])
    )
    result.edges.sort(
        key=lambda item: (
            item["jd_id"],
            slot_rank[item["resume_id"].rsplit("-", 1)[1]],
        )
    )
    result.usage = dict(actual_usage_total)
    result.valid_usage = dict(valid_usage_total)
    return result


def _targeted_direct_retry_rules(reason: str) -> list[str]:
    checks: tuple[tuple[tuple[str, ...], str], ...] = (
        (
            ("invalid_response_json", "response_json_not_object"),
            "只输出一个完整合法JSON对象，不要输出Markdown、代码围栏或解释。",
        ),
        (
            ("slot", "resumes_not_length_3"),
            "resumes必须恰好包含P1、P2、H1各一次，不能缺失、重复或增加slot。",
        ),
        (
            ("omitted_requirement_ids",),
            "P1/P2的omitted_requirement_ids必须为[]；H1填写1至2个输入中真实存在的R编号。",
        ),
        (
            ("label_leak", "negative_label_leak"),
            "从三份正文删除slot、样本、匹配、正负关系及“不会/缺少”等泄漏措辞。",
        ),
        (
            ("identity_or_contact",),
            "删除姓名字段和联系方式，学校与公司仅使用“某高校”“某科技企业”等匿名写法。",
        ),
        (
            ("near_duplicate",),
            "重写相似简历的职业路径、项目场景、技术路线、段落组织和措辞。",
        ),
        (
            ("length",),
            "将每份正文控制在硬范围500至1500字符，并尽量达到目标700至1100字符。",
        ),
        (
            ("timeline", "experience_", "seniority_experience"),
            "修正年月先后和工作经历总时长，使三份简历都符合权威经验年限与资历。",
        ),
    )
    rules = [
        rule
        for markers, rule in checks
        if any(marker in reason for marker in markers)
    ]
    rules.append(
        "保留原始JD事实边界和完整输出结构，重新返回三份完整简历JSON。"
    )
    return list(dict.fromkeys(rules))


def direct_retry_request(
    request: dict[str, Any],
    *,
    failure_reason: str,
    previous_output: Any,
    attempt: int = 1,
) -> dict[str, Any]:
    value = json.loads(json.dumps(request, ensure_ascii=False))
    base = re.sub(r"-r\d+$", "", str(value.get("custom_id") or ""))
    if direct_custom_id_jd_id(base) is None:
        raise ValueError("invalid direct custom_id")
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
    messages = value.setdefault("body", {}).setdefault("messages", [])
    if not isinstance(messages, list):
        raise ValueError("retry request body.messages must be a list")
    messages.append(
        {
            "role": "user",
            "content": (
                "上一次输出未通过本地严格校验。保留原JD输入，只修正失败项，"
                "重新返回完整合法JSON，不输出解释。\n"
                f"具体失败原因：{failure_reason}\n"
                "针对性修正规则：\n- "
                + "\n- ".join(_targeted_direct_retry_rules(failure_reason))
                + "\n上一次无效输出：\n"
                + (previous_text if previous_text else "（无可用输出）")
            ),
        }
    )
    return value


def build_direct_retry_requests(
    original_requests: Iterable[dict[str, Any]],
    failed_jd_ids: set[str],
    *,
    attempt: int = 1,
    failure_contexts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    failure_contexts = failure_contexts or {}
    retries: list[dict[str, Any]] = []
    for request in original_requests:
        custom_id = str(request.get("custom_id") or "")
        jd_id = direct_custom_id_jd_id(custom_id)
        if jd_id not in failed_jd_ids:
            continue
        context = failure_contexts.get(
            custom_id, failure_contexts.get(str(jd_id), {})
        )
        retries.append(
            direct_retry_request(
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
