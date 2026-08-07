from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from jd_resume_pipeline.batch_inputs import JOB_FAMILIES, force_edges
from jd_resume_pipeline.cleaning import normalize_compact
from jd_resume_pipeline.job_spec_semantics import (
    authoritative_semantics,
    evidence_in_record,
    evidence_supports_skill,
    group_contains_disallowed_non_skill_candidates,
    group_has_alternative_semantics,
    group_has_category_mixing,
    group_has_open_list_semantics,
    group_uses_preferred_semantics,
    minimum_required_for_group,
)
from jd_resume_pipeline.quality import SLOT_ORDER, ResumeQuality, evaluate_triplet


SENIORITIES = {
    "intern",
    "junior",
    "mid",
    "senior",
    "lead",
    "expert",
    "unspecified",
}
JOB_SPEC_ARRAY_FIELDS = (
    "required_skills",
    "preferred_skills",
    "core_tasks",
    "decisive_requirements",
)
JOB_SPEC_CUSTOM_ID_RE = re.compile(
    r"^job-spec-(J\d+)-v\d+(?:_\d+)*(?:-r\d+)?$"
)
RESUME_CUSTOM_ID_RE = re.compile(
    r"^resume-triplet-(J\d+)-v\d+(?:_\d+)*(?:-r\d+)?$"
)


@dataclass
class ParseFailure:
    custom_id: str
    jd_id: str | None
    reason: str


@dataclass
class JobSpecParseResult:
    job_specs: list[dict[str, Any]] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)
    # usage is actual API consumption from every HTTP-success response,
    # including responses later rejected by strict validation.
    usage: dict[str, int] = field(default_factory=dict)
    valid_usage: dict[str, int] = field(default_factory=dict)
    rejected_usage: dict[str, int] = field(default_factory=dict)
    api_successful_rows: int = 0
    strict_valid_rows: int = 0
    ignored_unexpected_rows: int = 0


@dataclass
class ResumeParseResult:
    resumes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)
    qualities: dict[str, ResumeQuality] = field(default_factory=dict)
    # Keep actual and strictly-valid usage separate for the same reason as
    # JobSpecParseResult.
    usage: dict[str, int] = field(default_factory=dict)
    valid_usage: dict[str, int] = field(default_factory=dict)
    api_successful_rows: int = 0
    strict_valid_rows: int = 0
    ignored_model_label_fields: int = 0


def custom_id_jd_id(custom_id: str, kind: str) -> str | None:
    pattern = JOB_SPEC_CUSTOM_ID_RE if kind == "job_spec" else RESUME_CUSTOM_ID_RE
    match = pattern.fullmatch(custom_id)
    return match.group(1) if match else None


def response_body(row: dict[str, Any]) -> dict[str, Any]:
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


def response_json_content(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    body = response_body(row)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    finish_reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
    if finish_reason not in (None, "stop"):
        raise ValueError(f"unexpected_finish_reason:{finish_reason}")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
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
    usage = normalize_usage(body.get("usage", {}))
    return value, usage


def normalize_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {}
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    total = usage.get("total_tokens", (prompt or 0) + (completion or 0))
    output: dict[str, int] = {}
    for key, value in (
        ("prompt_tokens", prompt),
        ("completion_tokens", completion),
        ("total_tokens", total),
    ):
        if isinstance(value, int) and value >= 0:
            output[key] = value
    return output


def add_usage(total: Counter[str], usage: dict[str, int]) -> None:
    total.update(usage)


def _required_skill_group_structure_errors(group: Any) -> list[str]:
    if not isinstance(group, dict):
        return ["required_skill_group_not_object"]
    errors: list[str] = []
    skills = group.get("skills")
    minimum = group.get("min_required")
    if group.get("mode") != "any_of":
        errors.append("invalid_required_skill_group_mode")
    evidence = group.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        errors.append("invalid_required_skill_group_evidence")
    if not isinstance(skills, list) or len(skills) < 1 or not all(
        isinstance(skill, str) and skill.strip() for skill in skills
    ):
        errors.append("invalid_required_skill_group_skills")
        skills = []
    elif len({normalize_compact(skill) for skill in skills}) != len(skills):
        errors.append("duplicate_required_skill_group_skills")
    if not isinstance(group.get("allow_other"), bool):
        errors.append("invalid_required_skill_group_allow_other")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or not (
        skills and 1 <= minimum <= len(skills)
    ):
        errors.append("invalid_required_skill_group_minimum")
    return errors


def validate_job_spec_structure(
    value: dict[str, Any],
    expected_jd_id: str,
    original_records: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if value.get("jd_id") != expected_jd_id:
        errors.append("jd_id_mismatch")
    if expected_jd_id not in original_records:
        errors.append("unknown_jd_id")
    if not isinstance(value.get("normalized_title"), str) or not value[
        "normalized_title"
    ].strip():
        errors.append("invalid_normalized_title")
    if value.get("job_family") not in JOB_FAMILIES:
        errors.append("invalid_job_family")
    if value.get("seniority") not in SENIORITIES:
        errors.append("invalid_seniority")
    for field_name in JOB_SPEC_ARRAY_FIELDS:
        field_value = value.get(field_name)
        if not isinstance(field_value, list) or not all(
            isinstance(item, str) and item.strip() for item in field_value
        ):
            errors.append(f"invalid_{field_name}")
    if isinstance(value.get("core_tasks"), list) and not value["core_tasks"]:
        errors.append("empty_core_tasks")
    if (
        isinstance(value.get("decisive_requirements"), list)
        and not value["decisive_requirements"]
    ):
        errors.append("empty_decisive_requirements")
    groups = value.get("required_skill_groups")
    if not isinstance(groups, list):
        errors.append("invalid_required_skill_groups")
        groups = []
    for group in groups:
        errors.extend(_required_skill_group_structure_errors(group))
    return errors


def _required_skill_group_semantic_errors(
    group: dict[str, Any],
    expected_jd_id: str,
    original_records: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    skills = group["skills"]
    evidence = group["evidence"]
    allow_other = group["allow_other"]
    minimum = group["min_required"]
    if expected_jd_id in original_records:
        original = original_records[expected_jd_id]
        if not evidence_in_record(original, evidence):
            errors.append("required_skill_group_evidence_not_found")
    if group_uses_preferred_semantics(evidence, skills):
        errors.append("required_skill_group_uses_preferred_evidence")
    if not group_has_alternative_semantics(evidence, skills):
        errors.append("required_skill_group_evidence_lacks_alternative_semantics")
    unsupported = [
        skill for skill in skills if not evidence_supports_skill(evidence, skill)
    ]
    if unsupported:
        errors.append("required_skill_group_skills_not_supported_by_evidence")
    evidence_is_open = group_has_open_list_semantics(evidence, skills)
    if allow_other != evidence_is_open:
        errors.append("required_skill_group_allow_other_evidence_mismatch")
    if len(skills) == 1 and not (allow_other is True and evidence_is_open):
        errors.append("singleton_required_skill_group_not_open")
    expected_minimum = minimum_required_for_group(evidence, skills)
    if expected_minimum is not None and minimum != expected_minimum:
        errors.append("required_skill_group_minimum_evidence_mismatch")
    if group_has_category_mixing(skills):
        errors.append("required_skill_group_mixes_candidate_categories")
    if group_contains_disallowed_non_skill_candidates(evidence, skills):
        errors.append("required_skill_group_contains_non_skill_candidates")
    return errors


def validate_required_skill_group(
    group: Any,
    expected_jd_id: str,
    original_records: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate one group for audit output without depending on sibling groups."""

    errors = _required_skill_group_structure_errors(group)
    if errors or not isinstance(group, dict):
        return errors
    return _required_skill_group_semantic_errors(
        group, expected_jd_id, original_records
    )


def validate_job_spec(
    value: dict[str, Any],
    expected_jd_id: str,
    original_records: dict[str, dict[str, Any]],
) -> list[str]:
    errors = validate_job_spec_structure(
        value, expected_jd_id, original_records
    )
    groups = value.get("required_skill_groups")
    flat_skills = value.get("required_skills")
    if not isinstance(groups, list):
        groups = []
    flat_normalized = (
        {normalize_compact(skill) for skill in flat_skills}
        if isinstance(flat_skills, list)
        else set()
    )
    seen_groups: set[tuple[str, ...]] = set()
    seen_group_skills: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        skills = group.get("skills")
        if not isinstance(skills, list) or len(skills) < 1 or not all(
            isinstance(skill, str) and skill.strip() for skill in skills
        ):
            continue
        if not _required_skill_group_structure_errors(group):
            errors.extend(
                _required_skill_group_semantic_errors(
                    group, expected_jd_id, original_records
                )
            )
        normalized_skills = tuple(
            sorted({normalize_compact(skill) for skill in skills if normalize_compact(skill)})
        )
        if normalized_skills in seen_groups:
            errors.append("duplicate_required_skill_group")
        seen_groups.add(normalized_skills)
        repeated_across_groups = seen_group_skills.intersection(normalized_skills)
        if repeated_across_groups:
            errors.append("required_skill_groups_overlap")
        seen_group_skills.update(normalized_skills)
        if flat_normalized.intersection(normalized_skills):
            errors.append("required_skill_group_flattening")

    if expected_jd_id in original_records:
        semantics = authoritative_semantics(original_records[expected_jd_id])
        if value.get("experience_requirement") != semantics["experience_requirement"]:
            errors.append("experience_requirement_mismatch")
        if value.get("seniority") != semantics["seniority"]:
            errors.append("seniority_mismatch")
    return errors


def parse_job_spec_rows(
    result_rows: Iterable[dict[str, Any]],
    original_records: dict[str, dict[str, Any]],
    expected_custom_ids: set[str] | None = None,
    api_error_reasons: dict[str, str] | None = None,
) -> JobSpecParseResult:
    result = JobSpecParseResult()
    actual_usage_total: Counter[str] = Counter()
    valid_usage_total: Counter[str] = Counter()
    seen_custom_ids: set[str] = set()
    successful_custom_ids: set[str] = set()
    api_error_reasons = api_error_reasons or {}

    for row in result_rows:
        custom_id = str(row.get("custom_id") or "")
        if expected_custom_ids is not None and custom_id not in expected_custom_ids:
            result.ignored_unexpected_rows += 1
            continue
        try:
            body = response_body(row)
        except ValueError:
            pass
        else:
            add_usage(actual_usage_total, normalize_usage(body.get("usage", {})))
            result.api_successful_rows += 1
        jd_id = custom_id_jd_id(custom_id, "job_spec")
        if not custom_id or custom_id in seen_custom_ids:
            result.failures.append(ParseFailure(custom_id, jd_id, "duplicate_or_missing_custom_id"))
            continue
        seen_custom_ids.add(custom_id)
        if jd_id is None:
            result.failures.append(ParseFailure(custom_id, None, "invalid_custom_id"))
            continue
        try:
            value, usage = response_json_content(row)
            errors = validate_job_spec(value, jd_id, original_records)
            if errors:
                raise ValueError(",".join(errors))
            add_usage(valid_usage_total, usage)
            result.strict_valid_rows += 1
            successful_custom_ids.add(custom_id)
            result.job_specs.append(
                {
                    "jd_id": jd_id,
                    "normalized_title": value["normalized_title"].strip(),
                    "job_family": value["job_family"],
                    "seniority": authoritative_semantics(
                        original_records[jd_id]
                    )["seniority"],
                    **{
                        field_name: list(dict.fromkeys(item.strip() for item in value[field_name]))
                        for field_name in JOB_SPEC_ARRAY_FIELDS
                    },
                    "required_skill_groups": [
                        {
                            "mode": "any_of",
                            "skills": list(
                                dict.fromkeys(
                                    skill.strip() for skill in group["skills"]
                                )
                            ),
                            "min_required": group["min_required"],
                            "allow_other": group["allow_other"],
                            "evidence": group["evidence"].strip(),
                        }
                        for group in value["required_skill_groups"]
                    ],
                    "experience_requirement": authoritative_semantics(
                        original_records[jd_id]
                    )["experience_requirement"],
                }
            )
        except ValueError as exc:
            result.failures.append(ParseFailure(custom_id, jd_id, str(exc)))

    if expected_custom_ids is not None:
        failed_ids = {failure.custom_id for failure in result.failures}
        for custom_id in sorted(expected_custom_ids - successful_custom_ids - failed_ids):
            result.failures.append(
                ParseFailure(
                    custom_id,
                    custom_id_jd_id(custom_id, "job_spec"),
                    api_error_reasons.get(custom_id, "missing_result"),
                )
            )
    result.job_specs.sort(key=lambda value: value["jd_id"])
    result.usage = dict(actual_usage_total)
    result.valid_usage = dict(valid_usage_total)
    result.rejected_usage = {
        key: actual_usage_total[key] - valid_usage_total[key]
        for key in sorted(set(actual_usage_total) | set(valid_usage_total))
    }
    return result


def validate_resume_payload(value: dict[str, Any], expected_jd_id: str) -> tuple[
    dict[str, dict[str, Any]], int, list[str]
]:
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
        ignored_labels += sum(
            key in resume for key in ("relevance", "relation", "label", "is_positive")
        )
        if not isinstance(resume.get("resume_text"), str):
            errors.append(f"{slot}:invalid_resume_text")
        by_slot[slot] = resume
    if set(by_slot) != set(SLOT_ORDER):
        errors.append("slots_not_exact")
    return by_slot, ignored_labels, errors


def parse_resume_rows(
    result_rows: Iterable[dict[str, Any]],
    job_specs: dict[str, dict[str, Any]],
    jd_texts: dict[str, str],
    expected_custom_ids: set[str] | None = None,
    api_error_reasons: dict[str, str] | None = None,
) -> ResumeParseResult:
    result = ResumeParseResult()
    actual_usage_total: Counter[str] = Counter()
    valid_usage_total: Counter[str] = Counter()
    seen_custom_ids: set[str] = set()
    successful_custom_ids: set[str] = set()
    api_error_reasons = api_error_reasons or {}

    for row in result_rows:
        try:
            body = response_body(row)
        except ValueError:
            pass
        else:
            add_usage(actual_usage_total, normalize_usage(body.get("usage", {})))
            result.api_successful_rows += 1
        custom_id = str(row.get("custom_id") or "")
        jd_id = custom_id_jd_id(custom_id, "resume")
        if not custom_id or custom_id in seen_custom_ids:
            result.failures.append(ParseFailure(custom_id, jd_id, "duplicate_or_missing_custom_id"))
            continue
        seen_custom_ids.add(custom_id)
        if jd_id is None:
            result.failures.append(ParseFailure(custom_id, None, "invalid_custom_id"))
            continue
        if jd_id not in job_specs or jd_id not in jd_texts:
            result.failures.append(ParseFailure(custom_id, jd_id, "missing_job_spec_or_jd"))
            continue
        try:
            value, usage = response_json_content(row)
            by_slot, ignored_labels, errors = validate_resume_payload(value, jd_id)
            result.ignored_model_label_fields += ignored_labels
            if errors:
                raise ValueError(",".join(errors))
            quality = evaluate_triplet(by_slot, job_specs[jd_id], jd_texts[jd_id])
            result.qualities[jd_id] = quality
            if not quality.passed:
                raise ValueError("quality:" + ",".join(quality.failures))
            add_usage(valid_usage_total, usage)
            result.strict_valid_rows += 1
            successful_custom_ids.add(custom_id)
            for slot in SLOT_ORDER:
                result.resumes.append(
                    {
                        "resume_id": f"{jd_id}-{slot}",
                        "resume_text": by_slot[slot]["resume_text"].strip(),
                        "slot": slot,
                    }
                )
            result.edges.extend(force_edges(jd_id))
        except ValueError as exc:
            result.failures.append(ParseFailure(custom_id, jd_id, str(exc)))

    if expected_custom_ids is not None:
        failed_ids = {failure.custom_id for failure in result.failures}
        for custom_id in sorted(expected_custom_ids - successful_custom_ids - failed_ids):
            result.failures.append(
                ParseFailure(
                    custom_id,
                    custom_id_jd_id(custom_id, "resume"),
                    api_error_reasons.get(custom_id, "missing_result"),
                )
            )
    slot_rank = {slot: index for index, slot in enumerate(SLOT_ORDER)}
    result.resumes.sort(
        key=lambda value: (
            value["resume_id"].rsplit("-", 1)[0],
            slot_rank[value["slot"]],
        )
    )
    result.edges.sort(
        key=lambda value: (
            value["jd_id"],
            slot_rank[value["resume_id"].rsplit("-", 1)[1]],
        )
    )
    result.usage = dict(actual_usage_total)
    result.valid_usage = dict(valid_usage_total)
    return result


def error_reasons(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
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


def previous_output_from_row(row: dict[str, Any]) -> Any:
    try:
        body = response_body(row)
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


def targeted_retry_rules(reason: str, kind: str) -> list[str]:
    rules: list[str] = []
    if kind == "job_spec":
        checks = (
            (
                (
                    "evidence_not_found",
                    "invalid_required_skill_group_evidence",
                ),
                "每个技能组的evidence必须逐字取自requirements或jd_text，不能改写。",
            ),
            (
                ("skills_not_supported_by_evidence",),
                "删除evidence未明确点名的候选技能；skills中的每一项都必须由同一evidence支持。",
            ),
            (
                ("lacks_alternative_semantics",),
                "普通并列不是any_of；没有“至少一种、任一、任选、A或B”等必需候选语义时删除该组。",
            ),
            (
                ("uses_preferred_evidence",),
                "含“优先、加分、更佳”的项目只能放入preferred_skills，必须从必需技能组删除。",
            ),
            (
                (
                    "singleton_required_skill_group_not_open",
                    "allow_other_evidence_mismatch",
                ),
                "封闭单元素组必须删除；仅开放示例列表可保留单元素组并设置allow_other=true。",
            ),
            (
                ("minimum_evidence_mismatch", "invalid_required_skill_group_minimum"),
                "min_required必须等于原文表达的最低候选数量。",
            ),
            (
                ("required_skill_group_flattening",),
                "从required_skills删除所有已进入required_skill_groups.skills的候选项。",
            ),
            (
                (
                    "required_skill_groups_overlap",
                    "duplicate_required_skill_group",
                    "duplicate_required_skill_group_skills",
                ),
                "候选技能在组内和组间都必须去重，同一技能只能出现一次。",
            ),
            (
                ("experience_requirement_mismatch",),
                "逐字段原样复制authoritative_experience_requirement。",
            ),
            (
                ("seniority_mismatch", "invalid_seniority"),
                "原样复制authoritative_seniority，不得自行推断。",
            ),
        )
        for markers, rule in checks:
            if any(marker in reason for marker in markers):
                rules.append(rule)
        rules.append(
            "重新检查所有required_skill_groups，宁可不建组，也不能把普通并列、技术栈组成部分或不同类型内容误建为any_of。"
        )
    else:
        rules.append(
            "针对本地质量失败逐项修正整个三简历JSON，保持P1/P2/H1槽位和程序标签约束。"
        )
    return list(dict.fromkeys(rules))


def retry_request(
    request: dict[str, Any],
    attempt: int = 1,
    *,
    failure_reason: str,
    previous_output: Any,
    kind: str,
) -> dict[str, Any]:
    value = json.loads(json.dumps(request, ensure_ascii=False))
    base = re.sub(r"-r\d+$", "", str(value["custom_id"]))
    value["custom_id"] = f"{base}-r{attempt}"
    if len(value["custom_id"]) > 256:
        raise ValueError("retry custom_id exceeds 256 characters")
    body = value.setdefault("body", {})
    messages = body.setdefault("messages", [])
    if not isinstance(messages, list):
        raise ValueError("retry request body.messages must be a list")
    previous_text = (
        previous_output
        if isinstance(previous_output, str)
        else json.dumps(
            previous_output,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "上一次输出未通过本地严格校验。请保留原任务输入，只修正失败项，"
                "并重新返回完整合法JSON；不要输出Markdown或解释。\n"
                f"具体失败原因：{failure_reason}\n"
                "针对性修正规则：\n- "
                + "\n- ".join(targeted_retry_rules(failure_reason, kind))
                + "\n上一次无效输出：\n"
                + (previous_text if previous_text else "（无可用输出）")
            ),
        }
    )
    return value


def build_retry_requests(
    original_requests: Iterable[dict[str, Any]],
    failed_jd_ids: set[str],
    kind: str,
    attempt: int = 1,
    failure_contexts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    failure_contexts = failure_contexts or {}
    for request in original_requests:
        custom_id = str(request.get("custom_id") or "")
        jd_id = custom_id_jd_id(custom_id, kind)
        if jd_id in failed_jd_ids:
            context = failure_contexts.get(custom_id, failure_contexts.get(jd_id, {}))
            output.append(
                retry_request(
                    request,
                    attempt,
                    failure_reason=str(
                        context.get("failure_reason")
                        or context.get("reason")
                        or "未提供失败原因"
                    ),
                    previous_output=context.get("previous_output"),
                    kind=kind,
                )
            )
    return output
