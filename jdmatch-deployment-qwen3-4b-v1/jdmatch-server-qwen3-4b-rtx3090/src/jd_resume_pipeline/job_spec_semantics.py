from __future__ import annotations

import re
from typing import Any, Iterable

from jd_resume_pipeline.cleaning import normalize_compact


EXPERIENCE_SOURCES = {"requirements", "jd_text", "metadata", "unspecified"}
ALTERNATIVE_MARKER_RE = re.compile(
    r"至少(?:掌握|熟悉|精通|使用|了解|具备)?[^。；;\n]{0,50}"
    r"(?:一种|一门|两种|两门|\d+\s*(?:种|门))|"
    r"(?:任意|任选|任一)(?:一种|一门|一项|其一|一者)?|"
    r"(?:一种|一门)(?:或多种|或多门)|"
    r"(?:其中)?(?:一种|一门)?(?:任选其一|任一|之一)",
    re.IGNORECASE,
)
ALTERNATIVE_LIST_RE = re.compile(
    r"[/／、,，]|(?:\s或\s)|(?:或[A-Za-z+#])", re.IGNORECASE
)
EXPLICIT_OR_RE = re.compile(
    r"(?:[\u4e00-\u9fffA-Za-z0-9+#.][\u4e00-\u9fffA-Za-z0-9+#.\- ]{0,30})"
    r"\s*(?:或|\bor\b)\s*"
    r"(?:[\u4e00-\u9fffA-Za-z0-9+#.][\u4e00-\u9fffA-Za-z0-9+#.\- ]{0,30})",
    re.IGNORECASE,
)
TECH_TOKEN = (
    r"[A-Za-z][A-Za-z0-9+#.]*"
    r"(?:\s+(?:Boot|Cloud|Framework|Studio|Core|NET|JS|SQL))?"
)
STRICT_TECH_OR_RE = re.compile(
    rf"(?<![A-Za-z0-9]){TECH_TOKEN}\s*(?:或|\bor\b)\s*{TECH_TOKEN}"
    rf"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
PREFERRED_MARKER_RE = re.compile(
    r"优先(?!级)|加分(?:项|要求)?|更佳|者佳|nice\s+to\s+have|bonus",
    re.IGNORECASE,
)
OPEN_LIST_MARKER_RE = re.compile(
    r"例如|比如|譬如|诸如|不限于|(?:包括|包含)[^。；;\n]{0,50}(?:等|等等)|"
    r"(?:等|等等)(?:框架|语言|工具|技术|技能|数据库|平台|软件|方案|均可|任选|至少|之一)?",
    re.IGNORECASE,
)
GROUP_RELATION_MARKER_RE = re.compile(
    r"至少(?:掌握|熟悉|精通|使用|了解|具备)?\s*"
    r"(?:\d+|[一二两三四五六七八九十])?\s*(?:种|门|项|个)|"
    r"(?:任意|任选|任一)(?:其中)?(?:一种|一门|一项|其一|一者)?|"
    r"(?:其中)?(?:一种|一门)?(?:任选其一|任一|之一)|"
    r"其中(?:一种|一门|一项|一个)|"
    r"(?:一种|一门)(?:或多种|或多门)|"
    r"中至少(?:\d+|[一二两三四五六七八九十])?\s*(?:种|门|项|个)",
    re.IGNORECASE,
)
OPEN_LIST_PREFIX_RE = re.compile(
    r"(?:例如|比如|譬如|诸如|如|包括但不限于|包含但不限于)"
    r"\s*[:：,，(（【\[]?\s*$",
    re.IGNORECASE,
)
OPEN_LIST_SUFFIX_RE = re.compile(
    r"^\s*[*_）)\]】]*\s*(?:等|等等)(?!级)",
    re.IGNORECASE,
)
LIST_SEPARATOR_RE = re.compile(
    r"^(?:\s|[*_、,，/／|]|和|与|及|以及|或|\bor\b|"
    r"优先|均可|也可|皆可|[\u4e00-\u9fff]{1,6}的)+$",
    re.IGNORECASE,
)
GROUP_STRONG_BOUNDARY_RE = re.compile(r"[。；;\n]")
PROGRAMMING_LANGUAGE_RE = re.compile(
    r"^(?:python|java|go|golang|node\.?js|javascript|typescript|"
    r"c|c\+\+|c/c\+\+|c#|bash|shell|linuxshell|scala|rust|matlab)$",
    re.IGNORECASE,
)
FRONTEND_FRAMEWORK_RE = re.compile(
    r"^(?:react|vue|angular|svelte|next\.?js|nuxt\.?js)$", re.IGNORECASE
)
BACKEND_FRAMEWORK_RE = re.compile(
    r"^(?:springboot|springcloud|spring|django|flask|fastapi|"
    r"express|nest\.?js|\.net)$",
    re.IGNORECASE,
)
DATABASE_RE = re.compile(
    r"^(?:mysql|postgresql|postgres|mongodb|oracle|sqlserver|sqlite|"
    r"redis|milvus|faiss|pinecone|chroma|elasticsearch)$",
    re.IGNORECASE,
)
MIDDLEWARE_RE = re.compile(
    r"^(?:kafka|rabbitmq|rocketmq|消息队列|中间件)$", re.IGNORECASE
)
CLOUD_PLATFORM_RE = re.compile(
    r"^(?:aws|azure|阿里云|腾讯云|华为云|gcp|googlecloud)$", re.IGNORECASE
)
VISUALIZATION_LIBRARY_RE = re.compile(r"^(?:vtk|vtk\.js)$", re.IGNORECASE)
GAME_ENGINE_RE = re.compile(r"^(?:unity|unreal)$", re.IGNORECASE)
ROBOTICS_MIDDLEWARE_RE = re.compile(r"^(?:ros|ros2)$", re.IGNORECASE)
GUI_FRAMEWORK_RE = re.compile(r"^(?:qt)$", re.IGNORECASE)
DISALLOWED_GROUP_SKILL_RE = re.compile(
    r"工程师$|专业$|学历$|证书$|认证$|"
    r"工业质检|工业巡检|生产监控|安全管控|"
    r"项目类型|任务类型|工作场景|业务场景",
    re.IGNORECASE,
)
MINIMUM_COUNT_RE = re.compile(
    r"(?:至少(?:掌握|熟悉|精通|使用|了解|具备)?[^。；;\n]{0,50}?|"
    r"(?:任意|任选|任一)(?:其中)?[^。；;\n]{0,20}?)"
    r"(?P<count>\d+|[一二两三四五六七八九十])\s*(?:种|门|项|个)",
    re.IGNORECASE,
)
YEAR_CONTEXT_RE = re.compile(
    r"经验|工作|从业|任职|研发|开发|算法|管理", re.IGNORECASE
)
YEAR_EXCLUSION_RE = re.compile(
    r"年龄|周岁|学制|毕业于|有效期|"
    r"(?:公司|企业|集团|机构).{0,30}(?:成立|创立|发展|深耕)|"
    r"(?:成立|创立)于?\s*\d{4}"
)
YEAR_RANGE_RE = re.compile(
    r"(?<!\d)(?P<minimum>\d{1,2})\s*(?:-|~|～|—|–|至|到)\s*"
    r"(?P<maximum>\d{1,2})\s*年"
)
YEAR_MINIMUM_RE = re.compile(
    r"(?:至少|不少于|不低于)?\s*(?<!\d)(?P<minimum>\d{1,2})\s*年"
    r"\s*(?:以上|及以上|或以上|起)?"
)
YEAR_BELOW_RE = re.compile(
    r"(?<!\d)(?P<maximum>\d{1,2})\s*年(?:以下|以内)"
)


def _unique_texts(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = re.sub(r"\s+", " ", str(value)).strip()
        canonical = re.sub(
            r"^[#*_\-\s]*(?:[（(]?\d{1,2}[）)、.．]\s*)?", "", value
        )
        key = normalize_compact(canonical)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _jd_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for line in text.replace("\r", "\n").splitlines():
        clauses.extend(re.split(r"(?<=[。；;])", line))
    return _unique_texts(clauses)


def has_preferred_semantics(text: str) -> bool:
    return bool(PREFERRED_MARKER_RE.search(str(text or "")))


def has_alternative_semantics(text: str) -> bool:
    clause = str(text or "")
    if has_preferred_semantics(clause):
        return False
    return bool(
        ALTERNATIVE_MARKER_RE.search(clause)
        or EXPLICIT_OR_RE.search(clause)
    )


def has_open_list_semantics(text: str) -> bool:
    return bool(OPEN_LIST_MARKER_RE.search(str(text or "")))


def _compact_text_with_positions(text: str) -> tuple[str, list[int]]:
    compact: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(str(text or "")):
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9+#.]", character):
            folded = character.casefold()
            compact.extend(folded)
            positions.extend([index] * len(folded))
    return "".join(compact), positions


def _skill_span(evidence: str, skill: str) -> tuple[int, int] | None:
    skill_text = str(skill or "").strip()
    if not skill_text:
        return None
    literal_pattern = re.escape(skill_text).replace(r"\ ", r"\s*")
    if re.fullmatch(r"[A-Za-z0-9+#.\s\-]+", skill_text):
        literal_pattern = rf"(?<![A-Za-z0-9]){literal_pattern}(?![A-Za-z0-9])"
    match = re.search(literal_pattern, evidence, re.IGNORECASE)
    if match:
        return match.span()

    evidence_compact, positions = _compact_text_with_positions(evidence)
    skill_compact = normalize_compact(skill_text)
    if not evidence_compact or not skill_compact:
        return None
    offset = evidence_compact.find(skill_compact)
    if offset < 0:
        return None
    return positions[offset], positions[offset + len(skill_compact) - 1] + 1


def _group_skill_spans(
    evidence: str, skills: Iterable[str]
) -> list[tuple[int, int]] | None:
    spans = [_skill_span(str(evidence or ""), str(skill)) for skill in skills]
    if any(span is None for span in spans):
        return None
    return sorted(span for span in spans if span is not None)


def _strong_clause_around(
    evidence: str, start: int, end: int
) -> tuple[str, int, int]:
    left_matches = list(GROUP_STRONG_BOUNDARY_RE.finditer(evidence, 0, start))
    left = left_matches[-1].end() if left_matches else 0
    right_match = GROUP_STRONG_BOUNDARY_RE.search(evidence, end)
    right = right_match.start() if right_match else len(evidence)
    return evidence[left:right], left, right


def _skills_form_local_list(evidence: str, spans: list[tuple[int, int]]) -> bool:
    if len(spans) < 2:
        return True
    return all(
        bool(LIST_SEPARATOR_RE.fullmatch(evidence[left_end:right_start]))
        for (_, left_end), (right_start, _) in zip(spans, spans[1:])
    )


def group_has_alternative_semantics(evidence: str, skills: Iterable[str]) -> bool:
    """Return whether the alternative marker is bound to this exact skill list.

    A bare slash is treated only as a list separator. It becomes an any-of
    relation when a local minimum/choice marker applies to that list. A direct
    ``A 或 B`` connector is sufficient when all group candidates form the same
    contiguous enumeration.
    """

    evidence_text = str(evidence or "")
    skill_list = [str(skill) for skill in skills]
    spans = _group_skill_spans(evidence_text, skill_list)
    if not spans or not _skills_form_local_list(evidence_text, spans):
        return False
    first_start = spans[0][0]
    last_end = spans[-1][1]
    clause, clause_start, _ = _strong_clause_around(
        evidence_text, first_start, last_end
    )
    relative_first = first_start - clause_start
    relative_last = last_end - clause_start
    relation_window = clause[
        max(0, relative_first - 40) : min(len(clause), relative_last + 40)
    ]
    if GROUP_RELATION_MARKER_RE.search(relation_window):
        return True
    if len(spans) < 2:
        return False
    separators = [
        evidence_text[left_end:right_start]
        for (_, left_end), (right_start, _) in zip(spans, spans[1:])
    ]
    return any(re.search(r"或|\bor\b", separator, re.IGNORECASE) for separator in separators)


def group_has_open_list_semantics(evidence: str, skills: Iterable[str]) -> bool:
    """Bind ``如/例如/包括但不限于/等`` to the current candidate list."""

    evidence_text = str(evidence or "")
    spans = _group_skill_spans(evidence_text, skills)
    if not spans or not _skills_form_local_list(evidence_text, spans):
        return False
    first_start = spans[0][0]
    last_end = spans[-1][1]
    clause, clause_start, clause_end = _strong_clause_around(
        evidence_text, first_start, last_end
    )
    relative_first = first_start - clause_start
    prefix = clause[max(0, relative_first - 24) : relative_first]
    suffix = evidence_text[last_end : min(clause_end, last_end + 12)]
    return bool(
        OPEN_LIST_PREFIX_RE.search(prefix)
        or OPEN_LIST_SUFFIX_RE.search(suffix)
    )


def group_uses_preferred_semantics(evidence: str, skills: Iterable[str]) -> bool:
    evidence_text = str(evidence or "")
    if not has_preferred_semantics(evidence_text):
        return False
    # A required quantified list may still name one preferred option, e.g.
    # “至少一门（Python优先，Java、Go均可）”. The group remains required.
    if (
        group_has_alternative_semantics(evidence_text, skills)
        and GROUP_RELATION_MARKER_RE.search(evidence_text)
        and re.search(r"均可|也可|皆可", evidence_text)
    ):
        return False
    return True


def skill_category(skill: str) -> str | None:
    compact = normalize_compact(str(skill or ""))
    if PROGRAMMING_LANGUAGE_RE.fullmatch(compact):
        return "programming_language"
    if FRONTEND_FRAMEWORK_RE.fullmatch(compact):
        return "frontend_framework"
    if BACKEND_FRAMEWORK_RE.fullmatch(compact):
        return "backend_framework"
    if DATABASE_RE.fullmatch(compact):
        return "database"
    if MIDDLEWARE_RE.fullmatch(compact):
        return "middleware"
    if CLOUD_PLATFORM_RE.fullmatch(compact):
        return "cloud_platform"
    if VISUALIZATION_LIBRARY_RE.fullmatch(compact):
        return "visualization_library"
    if GAME_ENGINE_RE.fullmatch(compact):
        return "game_engine"
    if ROBOTICS_MIDDLEWARE_RE.fullmatch(compact):
        return "robotics_middleware"
    if GUI_FRAMEWORK_RE.fullmatch(compact):
        return "gui_framework"
    return None


def group_has_category_mixing(skills: Iterable[str]) -> bool:
    categories = {
        category
        for skill in skills
        if (category := skill_category(str(skill))) is not None
    }
    return len(categories) > 1


def group_contains_disallowed_non_skill_candidates(
    evidence: str, skills: Iterable[str]
) -> bool:
    if any(DISALLOWED_GROUP_SKILL_RE.search(str(skill)) for skill in skills):
        return True
    return bool(
        re.search(r"至少(?:一个|一种|一类).{0,12}(?:场景|专业|证书|资格|研发领域)", evidence)
    )


def evidence_in_record(record: dict[str, Any], evidence: str) -> bool:
    evidence_key = normalize_compact(str(evidence or ""))
    if not evidence_key:
        return False
    sources = [
        *[str(value) for value in record.get("requirements", [])],
        str(record.get("jd_text") or ""),
    ]
    return any(evidence_key in normalize_compact(source) for source in sources)


def evidence_supports_skill(evidence: str, skill: str) -> bool:
    evidence_text = str(evidence or "")
    skill_text = str(skill or "").strip()
    skill_key = normalize_compact(skill_text)
    if not skill_key:
        return False

    # Compact matching deliberately normalizes case, whitespace and common
    # punctuation. Very short Latin tokens need boundaries so "Go" does not
    # accidentally match "Django".
    if re.fullmatch(r"[A-Za-z0-9+#.\s\-]+", skill_text) and len(skill_key) <= 3:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(skill_text.strip())}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        return bool(pattern.search(evidence_text))
    return skill_key in normalize_compact(evidence_text)


def minimum_required_from_evidence(evidence: str) -> int | None:
    match = MINIMUM_COUNT_RE.search(str(evidence or ""))
    if not match:
        return 1 if has_alternative_semantics(evidence) else None
    value = match.group("count")
    if value.isdigit():
        return int(value)
    chinese_numbers = {
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
    return chinese_numbers.get(value)


def minimum_required_for_group(
    evidence: str, skills: Iterable[str]
) -> int | None:
    evidence_text = str(evidence or "")
    spans = _group_skill_spans(evidence_text, skills)
    if not spans or not group_has_alternative_semantics(evidence_text, skills):
        return None
    clause, clause_start, _ = _strong_clause_around(
        evidence_text, spans[0][0], spans[-1][1]
    )
    relative_first = spans[0][0] - clause_start
    relative_last = spans[-1][1] - clause_start
    relation_window = clause[
        max(0, relative_first - 40) : min(len(clause), relative_last + 40)
    ]
    match = MINIMUM_COUNT_RE.search(relation_window)
    if not match:
        return 1
    value = match.group("count")
    if value.isdigit():
        return int(value)
    return {
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
    }.get(value)


def alternative_requirement_evidence(record: dict[str, Any]) -> list[str]:
    candidates = [
        *[str(value) for value in record.get("requirements", [])],
        *_jd_clauses(str(record.get("jd_text") or "")),
    ]
    output: list[str] = []
    for clause in _unique_texts(candidates):
        if has_preferred_semantics(clause):
            continue
        marker_with_list = (
            ALTERNATIVE_MARKER_RE.search(clause)
            and (
                ALTERNATIVE_LIST_RE.search(clause)
                or has_open_list_semantics(clause)
            )
        )
        if marker_with_list or STRICT_TECH_OR_RE.search(clause):
            output.append(clause)
    unique = _unique_texts(output)
    normalized = [normalize_compact(value) for value in unique]
    return [
        value
        for index, value in enumerate(unique)
        if not any(
            other_index != index
            and len(other) < len(normalized[index])
            and other in normalized[index]
            for other_index, other in enumerate(normalized)
        )
    ]


def _parse_year_clause(clause: str, source: str) -> list[dict[str, Any]]:
    if YEAR_EXCLUSION_RE.search(clause) or not YEAR_CONTEXT_RE.search(clause):
        return []
    output: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    def local_segment(match: re.Match[str]) -> str:
        left = max(
            clause.rfind(separator, 0, match.start())
            for separator in ("，", ",", "；", ";", "。")
        )
        right_candidates = [
            position
            for separator in ("，", ",", "；", ";", "。")
            if (position := clause.find(separator, match.end())) >= 0
        ]
        right = min(right_candidates) if right_candidates else len(clause)
        return clause[left + 1 : right].strip()

    def is_management(match: re.Match[str]) -> bool:
        return bool(re.search(r"管理|带团队|团队负责人", local_segment(match)))

    for match in YEAR_RANGE_RE.finditer(clause):
        minimum = int(match.group("minimum"))
        maximum = int(match.group("maximum"))
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        output.append(
            {
                "min_years": minimum,
                "max_years": maximum,
                "management": is_management(match),
                "source": source,
                "evidence": local_segment(match),
            }
        )
        occupied.append(match.span())
    for match in YEAR_BELOW_RE.finditer(clause):
        output.append(
            {
                "min_years": 0,
                "max_years": int(match.group("maximum")),
                "management": is_management(match),
                "source": source,
                "evidence": local_segment(match),
            }
        )
        occupied.append(match.span())
    for match in YEAR_MINIMUM_RE.finditer(clause):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        output.append(
            {
                "min_years": int(match.group("minimum")),
                "max_years": None,
                "management": is_management(match),
                "source": source,
                "evidence": local_segment(match),
            }
        )
    return output


def parse_metadata_experience(value: str | None) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text or re.search(r"不限|无经验|不要求", text):
        return None, None
    range_match = YEAR_RANGE_RE.search(text)
    if range_match:
        return int(range_match.group("minimum")), int(range_match.group("maximum"))
    below_match = YEAR_BELOW_RE.search(text)
    if below_match:
        return 0, int(below_match.group("maximum"))
    minimum_match = YEAR_MINIMUM_RE.search(text)
    if minimum_match:
        return int(minimum_match.group("minimum")), None
    return None, None


def authoritative_experience_requirement(record: dict[str, Any]) -> dict[str, Any]:
    requirement_clauses = _unique_texts(
        str(value) for value in record.get("requirements", [])
    )
    jd_clauses = _jd_clauses(str(record.get("jd_text") or ""))
    candidates: list[dict[str, Any]] = []
    for clause in requirement_clauses:
        candidates.extend(_parse_year_clause(clause, "requirements"))
    requirement_evidence_keys = {
        normalize_compact(candidate["evidence"]) for candidate in candidates
    }
    for clause in jd_clauses:
        if normalize_compact(clause) in requirement_evidence_keys:
            continue
        candidates.extend(_parse_year_clause(clause, "jd_text"))

    non_management = [candidate for candidate in candidates if not candidate["management"]]
    management = [candidate for candidate in candidates if candidate["management"]]
    metadata_min, metadata_max = parse_metadata_experience(record.get("experience"))

    if non_management:
        strongest_minimum = max(candidate["min_years"] for candidate in non_management)
        strongest = [
            candidate
            for candidate in non_management
            if candidate["min_years"] == strongest_minimum
        ]
        finite_maxima = [
            candidate["max_years"]
            for candidate in strongest
            if candidate["max_years"] is not None
        ]
        maximum = min(finite_maxima) if finite_maxima else None
        source = (
            "requirements"
            if any(candidate["source"] == "requirements" for candidate in strongest)
            else "jd_text"
        )
        minimum = strongest_minimum
    elif metadata_min is not None or metadata_max is not None:
        minimum, maximum, source = metadata_min, metadata_max, "metadata"
    else:
        minimum, maximum, source = None, None, "unspecified"

    management_minimum = (
        max(candidate["min_years"] for candidate in management) if management else None
    )
    body_authoritative = source in {"requirements", "jd_text"}
    metadata_conflict = body_authoritative and (
        metadata_min is not None or metadata_max is not None
    ) and (minimum, maximum) != (metadata_min, metadata_max)
    evidence = _unique_texts(
        candidate["evidence"]
        for candidate in candidates
        if (
            (not candidate["management"] and candidate["min_years"] == minimum)
            or (
                candidate["management"]
                and candidate["min_years"] == management_minimum
            )
        )
    )
    return {
        "min_years": minimum,
        "max_years": maximum,
        "management_min_years": management_minimum,
        "source": source,
        "metadata_conflict": metadata_conflict,
        "metadata_value": str(record.get("experience") or ""),
        "evidence": evidence,
    }


def derive_seniority(title: str, experience: dict[str, Any]) -> str:
    title = str(title or "")
    minimum = experience.get("min_years")
    if re.search(r"实习", title, re.I):
        return "intern"
    if (
        re.search(r"负责人|主管|经理|总监|架构师|\blead(?:er)?\b", title, re.I)
        and (minimum is None or minimum >= 3)
    ):
        return "lead"
    if (
        re.search(r"首席|科学家|资深专家|研究员", title, re.I)
        and (minimum is None or minimum >= 5)
    ):
        return "expert"
    if minimum is not None:
        if minimum <= 2:
            return "junior"
        if minimum <= 4:
            return "mid"
        if minimum <= 7:
            return "senior"
        return "expert"
    if re.search(r"初级|助理|应届|校招", title, re.I):
        return "junior"
    if re.search(r"高级|资深|\bsenior\b", title, re.I):
        return "senior"
    return "unspecified"


def authoritative_semantics(record: dict[str, Any]) -> dict[str, Any]:
    experience = authoritative_experience_requirement(record)
    return {
        "experience_requirement": experience,
        "seniority": derive_seniority(record.get("job_title", ""), experience),
        "alternative_requirement_evidence": alternative_requirement_evidence(record),
    }
