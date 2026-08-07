from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from jd_resume_pipeline.cleaning import normalize_compact


SLOT_ORDER = ("P1", "P2", "H1")
LABEL_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("slot_P1", re.compile(r"(?<![A-Za-z0-9])P1(?![A-Za-z0-9])", re.I)),
    ("slot_P2", re.compile(r"(?<![A-Za-z0-9])P2(?![A-Za-z0-9])", re.I)),
    ("slot_H1", re.compile(r"(?<![A-Za-z0-9])H1(?![A-Za-z0-9])", re.I)),
    ("positive", re.compile(r"positive", re.I)),
    ("negative", re.compile(r"negative", re.I)),
    ("匹配", re.compile(r"匹配")),
    ("正样本", re.compile(r"正样本")),
    ("负样本", re.compile(r"负样本")),
    ("硬负", re.compile(r"硬负")),
)
NEGATIVE_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("不会", re.compile(r"不会")),
    ("不熟悉", re.compile(r"不熟悉")),
    ("缺少", re.compile(r"缺少")),
    ("不具备", re.compile(r"不具备")),
    ("未接触", re.compile(r"未接触")),
)
IDENTITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("name_field", re.compile(r"(?:^|[\n；;])\s*姓名\s*[:：]", re.M)),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("wechat", re.compile(r"(?:微信|WeChat)\s*(?:号|ID)?\s*[:：]", re.I)),
    ("qq", re.compile(r"\bQQ\s*(?:号)?\s*[:：]?\s*\d{5,12}\b", re.I)),
    (
        "real_school_like",
        re.compile(r"(?<!某)(?<!一所)([\u4e00-\u9fff]{2,16}(?:大学|学院))"),
    ),
    (
        "real_company_like",
        re.compile(r"(?<!某)([\u4e00-\u9fff]{2,24}(?:有限公司|股份公司|集团公司))"),
    ),
)

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("大模型", "语言模型", "llm", "large language model"),
    ("智能体", "agent", "multiagent", "多智能体"),
    ("检索增强", "rag", "retrieval augmented generation"),
    ("计算机视觉", "机器视觉", "cv", "computer vision"),
    ("自然语言处理", "nlp", "natural language processing"),
    ("目标检测", "object detection"),
    ("语音识别", "asr", "speech recognition"),
    ("语音合成", "tts", "speech synthesis"),
    ("pytorch", "torch"),
    ("tensorflow", "tf"),
    ("c++", "cpp"),
)


@dataclass
class ResumeQuality:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def find_label_leaks(text: str) -> list[str]:
    return [name for name, pattern in LABEL_LEAK_PATTERNS if pattern.search(text)]


def find_negative_label_leaks(text: str) -> list[str]:
    return [name for name, pattern in NEGATIVE_LEAK_PATTERNS if pattern.search(text)]


def find_identity_leaks(text: str) -> list[str]:
    return [name for name, pattern in IDENTITY_PATTERNS if pattern.search(text)]


def _shingles(text: str, size: int = 4) -> set[str]:
    normalized = normalize_compact(text)
    if len(normalized) <= size:
        return {normalized} if normalized else set()
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def shingle_similarity(left: str, right: str, size: int = 4) -> float:
    left_shingles = _shingles(left, size)
    right_shingles = _shingles(right, size)
    union = left_shingles | right_shingles
    return len(left_shingles & right_shingles) / max(1, len(union))


def containment_copy_rate(source: str, candidate: str, size: int = 8) -> float:
    source_shingles = _shingles(source, size)
    candidate_shingles = _shingles(candidate, size)
    return len(source_shingles & candidate_shingles) / max(1, len(candidate_shingles))


def _concept_variants(concept: str) -> set[str]:
    normalized = normalize_compact(concept)
    variants = {normalized} if normalized else set()
    lower = concept.casefold()
    for group in SYNONYM_GROUPS:
        if any(normalize_compact(term) in normalized or term in lower for term in group):
            variants.update(normalize_compact(term) for term in group)
    technical_tokens = re.findall(
        r"[A-Za-z][A-Za-z0-9+#.]{1,30}|\d+\s*年|[\u4e00-\u9fff]{2,12}",
        concept,
    )
    stop_phrases = {
        "以上学历",
        "相关经验",
        "工作经验",
        "具备能力",
        "熟悉掌握",
        "能够完成",
        "实际经验",
        "项目经验",
        "优先考虑",
    }
    variants.update(
        normalize_compact(token)
        for token in technical_tokens
        if normalize_compact(token) not in stop_phrases
    )
    return {variant for variant in variants if len(variant) >= 2}


def concept_present(concept: str, text: str) -> bool:
    normalized_text = normalize_compact(text)
    variants = _concept_variants(concept)
    if not variants:
        return False
    if normalize_compact(concept) in normalized_text:
        return True
    return any(variant in normalized_text for variant in variants)


def decisive_coverage(requirements: Iterable[str], text: str) -> tuple[float, list[str]]:
    requirements = list(requirements)
    if not requirements:
        return 1.0, []
    missing = [requirement for requirement in requirements if not concept_present(requirement, text)]
    return (len(requirements) - len(missing)) / len(requirements), missing


def omitted_skill_violations(omitted_skills: Iterable[str], text: str) -> list[str]:
    return [skill for skill in omitted_skills if concept_present(skill, text)]


def _date_value(year: int, month: int) -> int:
    return year * 12 + month


DATE_RANGE_RE = re.compile(
    r"(?P<sy>20\d{2})[年./-](?P<sm>1[0-2]|0?[1-9])(?:月)?\s*"
    r"(?:至|到|—|–|-|~|～)\s*"
    r"(?:(?P<ey>20\d{2})[年./-](?P<em>1[0-2]|0?[1-9])(?:月)?|(?P<present>至今|现在))"
)


def timeline_errors(text: str) -> list[str]:
    errors: list[str] = []
    matches = list(DATE_RANGE_RE.finditer(text))
    if not matches:
        errors.append("missing_date_range")
    for match in matches:
        start = _date_value(int(match.group("sy")), int(match.group("sm")))
        if match.group("present"):
            continue
        end = _date_value(int(match.group("ey")), int(match.group("em")))
        if end < start:
            errors.append(match.group(0))
    malformed_months = re.findall(
        r"20\d{2}[年./-](?:0(?![1-9])|1[3-9]|[2-9]\d)(?:月)?", text
    )
    errors.extend(malformed_months)
    return errors


def work_experience_months(text: str) -> int | None:
    marker = text.find("工作经历")
    if marker < 0:
        return None
    scope = text[marker + len("工作经历") :]
    ends = [
        index
        for heading in ("项目经历", "教育经历", "技能", "职业摘要")
        if (index := scope.find(heading)) >= 0
    ]
    if ends:
        scope = scope[: min(ends)]
    intervals: list[tuple[int, int]] = []
    current = date.today()
    for match in DATE_RANGE_RE.finditer(scope):
        start = _date_value(int(match.group("sy")), int(match.group("sm")))
        if match.group("present"):
            end = _date_value(current.year, current.month)
        else:
            end = _date_value(int(match.group("ey")), int(match.group("em")))
        if end >= start:
            intervals.append((start, end))
    if not intervals:
        return None
    months: set[int] = set()
    for start, end in intervals:
        months.update(range(start, end + 1))
    return len(months)


def seniority_experience_error(seniority: str, months: int | None) -> bool:
    minimum_months = {
        "mid": 24,
        "senior": 48,
        "lead": 48,
        "expert": 84,
    }
    required = minimum_months.get(seniority)
    return required is not None and (months is None or months < required)


def _skills_present(skills: Iterable[str], text: str) -> set[str]:
    return {skill for skill in skills if concept_present(skill, text)}


def required_group_coverage(
    groups: Iterable[dict[str, Any]], text: str
) -> tuple[list[dict[str, Any]], list[int], list[int]]:
    selections: list[dict[str, Any]] = []
    underfilled: list[int] = []
    overfilled: list[int] = []
    for index, group in enumerate(groups):
        skills = group.get("skills", [])
        minimum = group.get("min_required", 1)
        selected = sorted(_skills_present(skills, text))
        selections.append(
            {
                "group_index": index,
                "selected_skills": selected,
                "selected_count": len(selected),
                "min_required": minimum,
            }
        )
        if len(selected) < minimum:
            underfilled.append(index)
        if minimum < len(skills) and len(selected) == len(skills):
            overfilled.append(index)
    return selections, underfilled, overfilled


def evaluate_triplet(
    resumes_by_slot: dict[str, dict[str, Any]],
    job_spec: dict[str, Any],
    jd_text: str,
    min_length: int = 700,
    max_length: int = 1100,
    near_duplicate_threshold: float = 0.72,
    max_jd_copy_rate: float = 0.25,
) -> ResumeQuality:
    failures: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {"slots": {}}

    if set(resumes_by_slot) != set(SLOT_ORDER):
        return ResumeQuality(False, ["slots_not_exact"], metrics=metrics)

    for slot in SLOT_ORDER:
        payload = resumes_by_slot[slot]
        text = payload.get("resume_text")
        if not isinstance(text, str) or not text.strip():
            failures.append(f"{slot}:missing_resume_text")
            continue
        length = visible_length(text)
        leaks = find_label_leaks(text)
        identity = find_identity_leaks(text)
        timeline = timeline_errors(text)
        experience_months = work_experience_months(text)
        copy_rate = containment_copy_rate(jd_text, text)
        coverage, missing = decisive_coverage(job_spec.get("decisive_requirements", []), text)
        required_coverage, missing_required = decisive_coverage(
            job_spec.get("required_skills", []), text
        )
        group_selections, underfilled_groups, overfilled_groups = required_group_coverage(
            job_spec.get("required_skill_groups", []), text
        )
        slot_metrics = {
            "length": length,
            "label_leaks": leaks,
            "identity_leaks": identity,
            "timeline_errors": timeline,
            "work_experience_months": experience_months,
            "jd_copy_rate": round(copy_rate, 4),
            "decisive_coverage": round(coverage, 4),
            "missing_decisive_requirements": missing,
            "required_skill_coverage": round(required_coverage, 4),
            "missing_required_skills": missing_required,
            "required_skill_group_selections": group_selections,
        }
        metrics["slots"][slot] = slot_metrics
        if not min_length <= length <= max_length:
            failures.append(f"{slot}:length")
        if leaks:
            failures.append(f"{slot}:label_leak")
        if identity:
            failures.append(f"{slot}:identity_or_contact")
        if timeline:
            failures.append(f"{slot}:timeline")
        if seniority_experience_error(
            str(job_spec.get("seniority") or "unspecified"), experience_months
        ):
            failures.append(f"{slot}:seniority_experience")
        if copy_rate > max_jd_copy_rate:
            failures.append(f"{slot}:jd_copy")
        if slot in {"P1", "P2"} and coverage < 1.0:
            failures.append(f"{slot}:decisive_coverage")
        if slot in {"P1", "P2"} and required_coverage < 1.0:
            failures.append(f"{slot}:required_skill_coverage")
        if slot in {"P1", "P2"} and underfilled_groups:
            failures.append(f"{slot}:required_skill_groups")
        if slot in {"P1", "P2"} and overfilled_groups:
            failures.append(f"{slot}:overfilled_any_of_group")
        experience_requirement = job_spec.get("experience_requirement", {})
        minimum_years = experience_requirement.get("min_years")
        maximum_years = experience_requirement.get("max_years")
        if slot in {"P1", "P2"} and isinstance(minimum_years, int) and (
            experience_months is None or experience_months < minimum_years * 12
        ):
            failures.append(f"{slot}:experience_minimum")
        if slot in {"P1", "P2"} and isinstance(maximum_years, int) and (
            experience_months is None or experience_months > maximum_years * 12 + 11
        ):
            failures.append(f"{slot}:experience_maximum")

    p1_text = str(resumes_by_slot["P1"].get("resume_text") or "")
    p2_text = str(resumes_by_slot["P2"].get("resume_text") or "")
    h1_text = str(resumes_by_slot["H1"].get("resume_text") or "")
    p_similarity = shingle_similarity(p1_text, p2_text)
    metrics["p1_p2_similarity"] = round(p_similarity, 4)
    if p_similarity >= near_duplicate_threshold:
        failures.append("P1_P2:near_duplicate")

    omitted = resumes_by_slot["H1"].get("omitted_core_skills")
    if not isinstance(omitted, list) or not omitted or not all(
        isinstance(skill, str) and skill.strip() for skill in omitted
    ):
        failures.append("H1:missing_omitted_core_skills")
        omitted = []
    violations = omitted_skill_violations(omitted, h1_text)
    metrics["h1_omitted_core_skills"] = omitted
    metrics["h1_omitted_skill_violations"] = violations
    if violations:
        failures.append("H1:omitted_skill_present")
    negative_leaks = find_negative_label_leaks(h1_text)
    metrics["h1_negative_label_leaks"] = negative_leaks
    if negative_leaks:
        failures.append("H1:negative_label_leak")

    required_skills = job_spec.get("required_skills", [])
    positive_skills = _skills_present(required_skills, p1_text) | _skills_present(
        required_skills, p2_text
    )
    h1_skills = _skills_present(required_skills, h1_text)
    overlap = len(positive_skills & h1_skills) / max(1, len(positive_skills))
    metrics["h1_common_skill_overlap"] = round(overlap, 4)
    if len(positive_skills) >= 3 and not 0.4 <= overlap <= 0.7:
        failures.append("H1:common_skill_overlap")
    if not positive_skills:
        warnings.append("required_skill_overlap_not_measurable")

    return ResumeQuality(not failures, sorted(set(failures)), warnings, metrics)


def summarize_failure_codes(qualities: Iterable[ResumeQuality]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for quality in qualities:
        counter.update(quality.failures)
    return dict(counter)
