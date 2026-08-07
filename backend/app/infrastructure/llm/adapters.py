"""Adapters that connect local LLM extraction to the v3 ports."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION
from backend.app.infrastructure.llm.client import ChatClientProtocol, OpenAICompatibleChatClient
from backend.app.infrastructure.llm.normalization import normalize_skills
from backend.app.infrastructure.llm.parser import ExtractionValidationError, parse_extraction_json
from backend.app.infrastructure.llm.prompts import extraction_messages
from backend.app.infrastructure.llm.settings import LLMSettings
from backend.app.infrastructure.mocks.adapters import NOT_IMPLEMENTED


class OllamaStructuredExtractor:
    def __init__(self, settings: LLMSettings, chat_client: ChatClientProtocol | None = None) -> None:
        self.settings = settings
        profile_settings = replace(settings, timeout_seconds=settings.profile_timeout_seconds)
        self.chat_client = chat_client or OpenAICompatibleChatClient(profile_settings)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        if document.document_type not in {DocumentType.RESUME, DocumentType.JD}:
            return _extraction_fallback(f"LLM extraction does not support document type '{document.document_type.value}'.")
        messages = extraction_messages(document, self.settings.max_input_chars)
        content = ""
        try:
            content = self.chat_client.chat(messages)
            fields = parse_extraction_json(content, document.document_type, source_text=document.text)
            warnings = list(fields.pop("_warnings", []))
            if document.document_type is DocumentType.JD:
                fields = _filter_salary_from_jd(fields)
        except ExtractionValidationError as exc:
            return _extraction_fallback(
                f"Ollama structured extraction failed: {exc}",
                raw_model_output=content,
                validation_error=str(exc),
            )
        except Exception as exc:
            return _extraction_fallback(
                f"Ollama structured extraction failed: {exc}",
                raw_model_output=content,
                validation_error=str(exc),
            )
        return {
            "state": "available",
            "implementation": "ollama",
            "model": self.settings.model,
            "schema": PROFILE_SCHEMA_VERSION,
            "fields": fields,
            "evidence": fields["evidence"],
            "warnings": warnings,
        }


class LightweightSkillNormalizer:
    def normalize(self, extraction: dict[str, Any]) -> dict[str, Any]:
        if extraction.get("state") != "available":
            return {
                "state": NOT_IMPLEMENTED,
                "implementation": "lightweight_skill_normalizer",
                "skills": [],
                "warnings": list(extraction.get("warnings", [])),
            }
        fields = dict(extraction.get("fields", {}))
        return {
            "state": "available",
            "implementation": "lightweight_skill_normalizer",
            "skills": normalize_skills(list(fields.get("skills", []))),
            "warnings": [],
        }


class LLMProfileBuilder:
    def build(
        self,
        profile_type: ProfileType,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]:
        if extraction.get("state") != "available":
            return _heuristic_profile(profile_type, document, extraction)
        fields = dict(extraction.get("fields", {}))
        attributes = _base_attributes(profile_type)
        normalized_skills = list(normalization.get("skills", []))
        attributes.update(
            {
                "profile_schema": PROFILE_SCHEMA_VERSION,
                "skills": normalized_skills,
                "capabilities": list(fields.get("capabilities", [])),
                "education": list(fields.get("education", [])),
                "experience": list(fields.get("experience", fields.get("work_experience", []))),
                "projects": list(fields.get("projects", fields.get("project_experience", []))),
            }
        )
        if profile_type is ProfileType.CANDIDATE:
            candidate = dict(fields.get("candidate", {}))
            career_intent = dict(fields.get("career_intent", {}))
            attributes["candidate"] = candidate
            attributes["career_intent"] = career_intent
            attributes["target_position"] = career_intent.get("target_position") or candidate.get("target_position")
            attributes["resume_profile"] = _resume_profile(fields, normalized_skills)
        else:
            job = dict(fields.get("job", {}))
            attributes["job"] = job
            # 多级回退获取岗位名称：LLM抽取 → 文档前50字符 → 默认值
            job_title = job.get("title") or job.get("normalized_title")
            if not job_title:
                job_title = _extract_title_from_text(document.text)
            attributes["job_title"] = job_title
            if not job.get("title") and job_title:
                job["title"] = job_title
                attributes["job"] = job
            attributes["requirements"] = list(fields.get("requirements", []))
            attributes["responsibilities"] = list(fields.get("responsibilities", []))
            attributes["company"] = dict(fields.get("company", {}))
            attributes["employment"] = dict(fields.get("employment", {}))
            attributes["jd_profile"] = _jd_profile(fields, normalized_skills)

        return {
            "state": "available",
            "implementation": "llm_profile_builder",
            "attributes": attributes,
            "evidence": list(fields.get("evidence", [])),
            "warnings": [
                *list(extraction.get("warnings", [])),
                *list(normalization.get("warnings", [])),
            ],
        }


def _extraction_fallback(
    reason: str,
    *,
    raw_model_output: str = "",
    validation_error: str = "",
) -> dict[str, Any]:
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "reason": reason,
        "fields": {},
        "evidence": [],
        "raw_model_output": raw_model_output[:4000],
        "validation_error": validation_error,
        "warnings": [reason],
    }


def _profile_fallback(profile_type: ProfileType, extraction: dict[str, Any]) -> dict[str, Any]:
    reason = str(extraction.get("reason") or "LLM structured extraction is unavailable.")
    warnings = [reason, *list(extraction.get("warnings", []))]
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "attributes": _base_attributes(profile_type),
        "evidence": [],
        "warnings": _deduplicate(warnings),
    }


def _heuristic_profile(
    profile_type: ProfileType,
    document: SourceDocument,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    text = document.text.strip()
    if not text:
        return _profile_fallback(profile_type, extraction)

    reason = str(extraction.get("reason") or "LLM structured extraction is unavailable.")
    evidence: list[dict[str, str]] = []
    attributes = _base_attributes(profile_type)
    skills = _extract_skill_items(text, evidence, profile_type)
    attributes["skills"] = skills

    if profile_type is ProfileType.CANDIDATE:
        _fill_candidate_heuristics(attributes, text, evidence)
    else:
        _fill_job_heuristics(attributes, text, evidence)

    warnings = _deduplicate(
        [
            reason,
            *list(extraction.get("warnings", [])),
            "Used heuristic profile extraction because LLM extraction was unavailable.",
        ]
    )
    return {
        "state": "available",
        "implementation": "heuristic_profile_builder",
        "attributes": attributes,
        "evidence": evidence,
        "warnings": warnings,
    }


def _base_attributes(profile_type: ProfileType) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "profile_schema": PROFILE_SCHEMA_VERSION,
        "skills": [],
        "capabilities": [],
        "education": [],
        "experience": [],
        "projects": [],
    }
    if profile_type is ProfileType.JOB:
        attributes.update(
            {
                "job": {},
                "job_title": None,
                "company": {},
                "employment": {},
                "requirements": [],
                "responsibilities": [],
                "jd_profile": {},
            }
        )
    else:
        attributes.update({"candidate": {}, "career_intent": {}, "target_position": None, "resume_profile": {}})
    return attributes


def _fill_candidate_heuristics(attributes: dict[str, Any], text: str, evidence: list[dict[str, str]]) -> None:
    lines = _clean_lines(text)
    name = _value_after_label(lines, ("姓名", "名字", "候选人", "应聘者"))
    target_position = _value_after_label(lines, ("求职岗位", "目标岗位", "应聘岗位", "求职意向"))
    education_text = _value_after_label(lines, ("学历", "教育背景", "毕业院校", "学校"))
    experience_text = _value_after_label(lines, ("工作经验", "工作经历", "项目经验", "经历"))

    candidate = {
        "name": name,
        "current_title": target_position,
        "years_of_experience": _extract_years(text),
        "location": _value_after_label(lines, ("所在地", "现居地", "城市", "地点")),
        "target_position": target_position,
    }
    career_intent = {
        "target_position": target_position,
        "target_industry": None,
        "target_location": None,
    }
    attributes["candidate"] = {key: value for key, value in candidate.items() if value is not None}
    attributes["career_intent"] = {key: value for key, value in career_intent.items() if value is not None}
    attributes["target_position"] = target_position

    if education_text:
        ev_id = _add_evidence(evidence, "education", education_text)
        attributes["education"] = [{"degree": education_text, "school": None, "major": None, "period": None, "evidence_ids": [ev_id]}]
    if experience_text:
        ev_id = _add_evidence(evidence, "experience", experience_text)
        attributes["experience"] = [{"description": experience_text, "evidence_ids": [ev_id]}]

    attributes["resume_profile"] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.RESUME.value,
        "candidate": attributes["candidate"],
        "career_intent": attributes["career_intent"],
        "education": attributes["education"],
        "work_experience": attributes["experience"],
        "project_experience": attributes["projects"],
        "skills": attributes["skills"],
        "capabilities": attributes["capabilities"],
        "certificates": [],
        "languages": [],
        "achievements": [],
    }


def _fill_job_heuristics(attributes: dict[str, Any], text: str, evidence: list[dict[str, str]]) -> None:
    lines = _clean_lines(text)
    title = _value_after_label(lines, ("岗位名称", "职位名称", "招聘岗位", "职位")) or _extract_title_from_text(text)
    company_name = _value_after_label(lines, ("公司名称", "公司", "企业"))
    location = _value_after_label(lines, ("工作地点", "地点", "工作城市", "城市"))
    department = _value_after_label(lines, ("所属部门", "部门"))
    salary_text = _value_after_label(lines, ("薪资范围", "薪资", "薪酬"))

    attributes["job"] = {
        "title": title,
        "normalized_title": title,
        "department": department,
        "seniority": None,
    }
    attributes["job_title"] = title
    attributes["company"] = {"name": company_name, "industry": None, "location": location}
    attributes["employment"] = {
        "employment_type": "full_time",
        "salary_min": None,
        "salary_max": None,
        "salary_range": salary_text,
        "published_at": None,
    }

    responsibilities = _section_items(
        lines,
        ("岗位职责", "工作职责", "职责描述", "工作内容"),
        ("任职要求", "岗位要求", "任职资格", "能力要求", "薪资", "福利"),
    )
    requirements = _section_items(
        lines,
        ("任职要求", "岗位要求", "任职资格", "能力要求"),
        ("岗位职责", "工作职责", "薪资", "福利", "工作地点"),
    )
    attributes["responsibilities"] = [
        {
            "text": item,
            "action": "",
            "object": "",
            "evidence_ids": [_add_evidence(evidence, "responsibilities", item)],
        }
        for item in responsibilities[:8]
    ]
    attributes["requirements"] = [
        {
            "text": item,
            "requirement_type": _requirement_type(item),
            "importance": _importance(item),
            "evidence_ids": [_add_evidence(evidence, "requirements", item)],
        }
        for item in requirements[:8]
    ]
    attributes["jd_profile"] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.JD.value,
        "job": attributes["job"],
        "company": attributes["company"],
        "employment": attributes["employment"],
        "responsibilities": attributes["responsibilities"],
        "requirements": attributes["requirements"],
        "skills": attributes["skills"],
        "capabilities": attributes["capabilities"],
        "application_scenarios": [],
        "evaluation_signals": [],
    }


def _clean_lines(text: str) -> list[str]:
    return [line.strip(" \t\r\n-•*") for line in text.splitlines() if line.strip()]


def _value_after_label(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for line in lines[:30]:
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*[:：|｜]\s*([^|｜\n]+)", line)
            if match:
                return match.group(1).strip()[:120] or None
    return None


def _section_items(lines: list[str], starts: tuple[str, ...], stops: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    collecting = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if any(start in line for start in starts):
            collecting = True
            continue
        if collecting and any(stop in line for stop in stops):
            break
        if collecting and len(line) >= 6:
            items.append(line[:180])
    return items


def _extract_skill_items(
    text: str,
    evidence: list[dict[str, str]],
    profile_type: ProfileType,
) -> list[dict[str, Any]]:
    skill_names = (
        "Python",
        "Java",
        "C++",
        "JavaScript",
        "TypeScript",
        "React",
        "Vue",
        "Node.js",
        "SQL",
        "MySQL",
        "PostgreSQL",
        "Redis",
        "Docker",
        "Kubernetes",
        "Linux",
        "Git",
        "PyTorch",
        "TensorFlow",
        "NLP",
        "Prompt",
        "RAG",
        "AIGC",
        "大模型",
        "机器学习",
        "深度学习",
        "自然语言处理",
        "向量数据库",
        "知识库",
        "数据清洗",
        "数据分析",
        "微调",
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in skill_names:
        if name.casefold() in seen:
            continue
        if re.search(re.escape(name), text, flags=re.IGNORECASE):
            seen.add(name.casefold())
            ev_id = _add_evidence(evidence, "skills", _quote_for_term(text, name))
            item: dict[str, Any] = {
                "name": name,
                "raw_name": name,
                "category": _skill_category(name),
                "lskt_label": "S",
                "evidence_ids": [ev_id],
            }
            if profile_type is ProfileType.JOB:
                item["importance"] = "unknown"
            else:
                item["level"] = "unknown"
                item["years"] = None
            items.append(item)
    return items[:20]


def _add_evidence(evidence: list[dict[str, str]], field: str, text: str) -> str:
    quote = re.sub(r"\s+", " ", text).strip()[:120] or field
    evidence_id = f"ev_{len(evidence) + 1:03d}"
    evidence.append({"id": evidence_id, "field": field, "text": quote})
    return evidence_id


def _quote_for_term(text: str, term: str) -> str:
    match = re.search(re.escape(term), text, flags=re.IGNORECASE)
    if not match:
        return term
    start = max(0, match.start() - 30)
    end = min(len(text), match.end() + 30)
    return text[start:end].replace("\n", " ")


def _extract_years(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:年|years?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _skill_category(name: str) -> str:
    if name in {"Python", "Java", "C++", "JavaScript", "TypeScript"}:
        return "programming_language"
    if name in {"React", "Vue", "Node.js", "PyTorch", "TensorFlow"}:
        return "framework"
    if name in {"MySQL", "PostgreSQL", "Redis", "SQL", "向量数据库", "知识库"}:
        return "database"
    if name in {"Docker", "Kubernetes", "Linux", "Git"}:
        return "devops"
    if name in {"大模型", "机器学习", "深度学习", "自然语言处理", "NLP", "AIGC"}:
        return "ai_model"
    return "other"


def _requirement_type(text: str) -> str:
    if any(key in text for key in ("学历", "本科", "硕士", "博士", "专业")):
        return "education"
    if any(key in text for key in ("经验", "年")):
        return "experience"
    if any(key in text for key in ("熟悉", "掌握", "技能", "开发", "模型", "Prompt", "Python")):
        return "skill"
    if any(key in text for key in ("证书", "认证")):
        return "certificate"
    return "other"


def _importance(text: str) -> str:
    if any(key in text for key in ("优先", "加分", "更佳")):
        return "preferred"
    if any(key in text for key in ("必须", "要求", "熟悉", "掌握", "负责")):
        return "required"
    return "unknown"


def _resume_profile(fields: dict[str, Any], skills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.RESUME.value,
        "candidate": dict(fields.get("candidate", {})),
        "career_intent": dict(fields.get("career_intent", {})),
        "education": list(fields.get("education", [])),
        "work_experience": list(fields.get("work_experience", fields.get("experience", []))),
        "project_experience": list(fields.get("project_experience", fields.get("projects", []))),
        "skills": skills,
        "capabilities": list(fields.get("capabilities", [])),
        "certificates": list(fields.get("certificates", [])),
        "languages": list(fields.get("languages", [])),
        "achievements": list(fields.get("achievements", [])),
    }


def _jd_profile(fields: dict[str, Any], skills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.JD.value,
        "job": dict(fields.get("job", {})),
        "company": dict(fields.get("company", {})),
        "employment": dict(fields.get("employment", {})),
        "responsibilities": list(fields.get("responsibilities", [])),
        "requirements": list(fields.get("requirements", [])),
        "skills": skills,
        "capabilities": list(fields.get("capabilities", [])),
        "application_scenarios": list(fields.get("application_scenarios", [])),
        "evaluation_signals": list(fields.get("evaluation_signals", [])),
    }


def _extract_title_from_text(text: str) -> str | None:
    """从文档文本中提取岗位名称作为兜底。"""
    if not text:
        return None
    # 取前5行非空行，寻找可能的岗位名称
    lines = [line.strip() for line in text.split("\n") if line.strip()][:5]
    for line in lines:
        # 跳过过长的行（可能是描述而非标题）
        if len(line) > 60:
            continue
        # 跳过纯数字、纯符号、日期等
        if re.match(r"^[\d\s\-/\.]+$", line):
            continue
        # 跳过常见非标题行
        if any(kw in line.lower() for kw in ["公司", "地址", "电话", "邮箱", "email", "http", "www"]):
            continue
        # 看起来像岗位名称的行（包含"工程师"、"开发"、"设计"等关键词，或者是较短的行）
        title_keywords = ["工程师", "开发", "设计", "经理", "主管", "总监", "专员", "分析师", "架构师",
                         "测试", "运维", "产品", "运营", "前端", "后端", "算法", "数据", "AI", "机器学习",
                         "深度学习", "大模型", "Agent", "Python", "Java", "Go", "C++", "JavaScript"]
        if any(kw in line for kw in title_keywords):
            return line
        # 如果前3行中有一行较短（<30字符），可能是标题
        if len(line) < 30 and lines.index(line) < 3:
            return line
    return None


def _deduplicate(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


# ── Post-processing: filter salary/benefits from JD responsibilities/requirements ──

_SALARY_BENEFIT_KEYWORDS = (
    "薪资", "工资", "薪酬", "月薪", "年薪", "k-", "K-",
    "五险一金", "六险一金", "双休", "奖金", "补贴", "餐补",
    "交通补", "住房补", "带薪年假", "带薪病假", "节日福利",
    "年终奖", "绩效奖", "股票", "期权", "社保", "公积金",
    "加班费", "加班补贴", "项目奖金", "技术晋升", "晋升通道",
    "员工旅游", "团建", "体检", "商业保险", "免费", "包吃",
    "包住", "包午餐", "「", "」", "【", "】",
)


def _is_salary_or_benefit(text: str) -> bool:
    """Check if a line looks like salary/benefits info rather than a job duty or requirement."""
    t = text.strip().lower()
    # Lines starting with a salary pattern like "9k-16k", "15-25K", "10k-20k"
    if re.match(r"^\d+[kK]\s*[-~～]", t):
        return True
    # Lines that are primarily salary/benefits content
    hit = sum(1 for kw in _SALARY_BENEFIT_KEYWORDS if kw in text)
    if hit >= 2:
        return True
    # Short lines that are purely about compensation
    if len(text) < 40 and hit >= 1 and not any(
        duty_kw in text for duty_kw in ("负责", "参与", "完成", "开发", "设计", "维护", "管理", "协助", "推动", "熟悉", "掌握", "具备", "了解", "本科", "硕士", "学历", "经验", "年以上")
    ):
        return True
    return False


def _filter_salary_from_jd(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove salary/benefits items from responsibilities and requirements."""
    for key in ("responsibilities", "requirements"):
        items = fields.get(key)
        if not isinstance(items, list):
            continue
        filtered = [item for item in items if not _is_salary_or_benefit(
            item.get("text", "") if isinstance(item, dict) else str(item)
        )]
        fields[key] = filtered
    return fields


# ── LLM-based Matcher ───────────────────────────────────

MATCH_SYSTEM_PROMPT = """你是人岗匹配评估专家。根据候选人画像和岗位画像，评估匹配程度。
只输出一个合法 JSON object，不要输出 Markdown、解释或额外文字。
评分标准：
- 80-100：高度匹配，候选人技能和经验完全符合岗位要求
- 60-79：较为匹配，候选人基本符合要求，有少量差距
- 40-59：部分匹配，候选人有一定基础但差距明显
- 0-39：匹配度低，候选人与岗位要求差距较大"""

MATCH_SCHEMA = """输出 JSON schema:
{
  "score": 0-100 的整数,
  "decision": "strong_match|match|partial_match|weak_match|mismatch",
  "skill_score": 0-100,
  "knowledge_score": 0-100,
  "experience_score": 0-100,
  "ability_score": 0-100,
  "strengths": [{"category": "skill|knowledge|experience|ability", "text": "具体优势描述", "evidence": "依据"}],
  "gaps": [{"category": "skill|knowledge|experience|ability", "text": "具体差距描述", "importance": "required|preferred", "suggestion": "提升建议"}],
  "learning_path": [{"skill": "技能名", "priority": "high|medium|low", "resource": "学习建议"}],
  "summary": "一句话总结匹配结论"
}"""


class LLMMatcher:
    """LLM-based person-job matcher."""

    def __init__(self, settings: LLMSettings, chat_client: ChatClientProtocol | None = None) -> None:
        self.settings = settings
        match_settings = replace(settings, timeout_seconds=settings.match_timeout_seconds)
        self.chat_client = chat_client or OpenAICompatibleChatClient(match_settings)

    def assess(self, candidate: Any, job: Any, options: dict[str, Any]) -> dict[str, Any]:
        cand_attrs = candidate.attributes if hasattr(candidate, "attributes") else {}
        job_attrs = job.attributes if hasattr(job, "attributes") else {}

        cand_skills = [s.get("name", "") for s in cand_attrs.get("skills", [])]
        job_skills = [s.get("name", "") for s in job_attrs.get("skills", [])]
        cand_exp = cand_attrs.get("work_experience", cand_attrs.get("experience", []))
        job_reqs = job_attrs.get("requirements", [])
        job_resp = job_attrs.get("responsibilities", [])

        user_prompt = f"""候选人画像：
- 技能：{', '.join(cand_skills) if cand_skills else '无'}
- 工作经历：{json.dumps(cand_exp, ensure_ascii=False)[:2000]}
- 教育：{json.dumps(cand_attrs.get('education', []), ensure_ascii=False)[:500]}
- 项目：{json.dumps(cand_attrs.get('projects', []), ensure_ascii=False)[:1000]}

岗位画像：
- 技能要求：{', '.join(job_skills) if job_skills else '无'}
- 岗位职责：{json.dumps(job_resp, ensure_ascii=False)[:1500]}
- 岗位要求：{json.dumps(job_reqs, ensure_ascii=False)[:1500]}

{MATCH_SCHEMA}"""

        messages = [
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = self.chat_client.chat(messages)
            result = json.loads(content.strip())
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")
        except Exception as exc:
            return _fallback_match_result(cand_attrs, job_attrs, str(exc))

        # Extract dimension scores
        details = {}
        for dim in ("skill_score", "knowledge_score", "experience_score", "ability_score"):
            if dim in result and isinstance(result[dim], (int, float)):
                details[dim] = max(0, min(100, int(result[dim])))

        try:
            score = max(0, min(100, int(result.get("score", 0))))
            strengths = result.get("strengths", [])
            gaps = result.get("gaps", [])
            learning_path = result.get("learning_path", [])
            if not all(isinstance(value, list) for value in (strengths, gaps, learning_path)):
                raise ValueError("match result list fields were invalid")
        except (TypeError, ValueError) as exc:
            return _fallback_match_result(cand_attrs, job_attrs, f"invalid LLM match result: {exc}")

        return {
            "state": "available",
            "implementation": "llm_matcher",
            "score": score,
            "decision": result.get("decision", "partial_match"),
            "strengths": strengths,
            "gaps": gaps,
            "learning_path": learning_path,
            "document_evidence": [],
            "graph_evidence": [],
            "details": details,
            "summary": result.get("summary", ""),
            "warnings": [],
        }


def _fallback_match_result(
    candidate_attrs: dict[str, Any],
    job_attrs: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Return a useful local result when the LLM is unavailable or times out."""
    candidate_skills = _match_skill_names(candidate_attrs.get("skills", []))
    job_skills = _match_skill_names(job_attrs.get("skills", []))
    # Some valid profiles put required skills only in requirement objects.
    for requirement in job_attrs.get("requirements", []):
        if not isinstance(requirement, dict) or requirement.get("requirement_type") != "skill":
            continue
        text = str(requirement.get("text") or "").strip()
        if text and text not in job_skills:
            job_skills.append(text)

    candidate_keys = {_match_key(value): value for value in candidate_skills if _match_key(value)}
    matched: list[str] = []
    missing: list[str] = []
    for required in job_skills:
        required_key = _match_key(required)
        found = next(
            (value for key, value in candidate_keys.items() if key == required_key or key in required_key or required_key in key),
            None,
        )
        if found:
            if found not in matched:
                matched.append(found)
        else:
            missing.append(required)

    skill_score = round(len(matched) / len(job_skills) * 100) if job_skills else 50
    has_experience = bool(candidate_attrs.get("experience") or candidate_attrs.get("work_experience"))
    has_projects = bool(candidate_attrs.get("projects") or candidate_attrs.get("project_experience"))
    experience_score = 75 if has_experience else (55 if has_projects else 25)
    ability_score = 75 if (candidate_attrs.get("capabilities") or has_projects) else 45
    knowledge_score = min(100, round(skill_score * 0.8 + (20 if has_experience else 0)))
    score = round(skill_score * 0.55 + knowledge_score * 0.2 + experience_score * 0.15 + ability_score * 0.1)
    if score >= 80:
        decision = "strong_match"
    elif score >= 60:
        decision = "match"
    elif score >= 40:
        decision = "partial_match"
    else:
        decision = "weak_match"

    strengths = [
        {"category": "skill", "text": f"已匹配 {len(matched)} 项岗位技能。", "evidence": "profile.skills"}
    ] if matched else []
    gaps = [
        {
            "category": "skill",
            "text": f"缺少岗位技能：{', '.join(missing[:8])}。",
            "importance": "required",
            "suggestion": "针对缺失技能安排课程或项目实践。",
        }
    ] if missing else []
    learning_path = [
        {"skill": skill, "priority": "high", "resource": "结合岗位项目进行实践。"}
        for skill in missing[:5]
    ]
    return {
        "state": "available",
        "implementation": "deterministic_matcher_fallback",
        "score": score,
        "decision": decision,
        "strengths": strengths,
        "gaps": gaps,
        "learning_path": learning_path,
        "document_evidence": [],
        "graph_evidence": [],
        "details": {
            "skill_score": skill_score,
            "knowledge_score": knowledge_score,
            "experience_score": experience_score,
            "ability_score": ability_score,
        },
        "summary": "本地模型暂不可用，已使用技能与经历规则完成匹配。",
        "warnings": [f"LLM matcher fallback: {reason}"],
    }


def _match_skill_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for value in values:
        name = value.get("name") if isinstance(value, dict) else value
        name = str(name or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _match_key(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())


class LLMReportGenerator:
    """LLM-based match report generator."""

    def __init__(self, settings: LLMSettings, chat_client: ChatClientProtocol | None = None) -> None:
        self.settings = settings
        self.chat_client = chat_client or OpenAICompatibleChatClient(settings)

    def generate(self, match: Any, language: str) -> dict[str, Any]:
        match_data = match.public() if hasattr(match, "public") else {}
        score = match_data.get("score")
        strengths = match_data.get("strengths", [])
        gaps = match_data.get("gaps", [])
        learning_path = match_data.get("learning_path", [])

        user_prompt = f"""基于以下人岗匹配结果，生成一份简洁的中文匹配报告。

匹配得分：{score}/100
决策：{match_data.get('decision', '未知')}
优势：{json.dumps(strengths, ensure_ascii=False)[:1500]}
差距：{json.dumps(gaps, ensure_ascii=False)[:1500]}
学习路径：{json.dumps(learning_path, ensure_ascii=False)[:1000]}

请生成包含以下部分的报告：
1. 匹配概要（一句话总结）
2. 核心优势（2-3条）
3. 关键差距（2-3条）
4. 提升建议（具体可执行的建议）
5. 综合评价

只输出纯文本，不要用 Markdown 格式。"""

        messages = [
            {"role": "system", "content": "你是 HR 技术顾问，擅长撰写人岗匹配分析报告。输出简洁专业的中文报告。"},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = self.chat_client.chat(messages)
        except Exception as exc:
            return {
                "state": "error",
                "implementation": "llm_report_error",
                "sections": [],
                "content": f"报告生成失败: {exc}",
                "warnings": [str(exc)],
            }

        return {
            "state": "available",
            "implementation": "llm_report_generator",
            "sections": [{"title": "匹配报告", "content": content}],
            "content": content,
            "warnings": [],
        }


# ── LLM-based Learning Advisor ─────────────────────────

LEARNING_ADVICE_SYSTEM_PROMPT = """你是职业发展顾问和技能培训专家。根据人岗匹配结果中的差距，为候选人提供详细、可执行的学习建议。
只输出一个合法 JSON object，不要输出 Markdown、解释或额外文字。
建议要具体、可操作，包含学习步骤、推荐资源和预计时间。"""

LEARNING_ADVICE_SCHEMA = """输出 JSON schema:
{
  "summary": "一句话总结学习方向",
  "skill_gaps": [
    {
      "skill": "技能名称",
      "current_level": "当前水平描述",
      "target_level": "目标水平描述",
      "priority": "high|medium|low",
      "learning_steps": ["步骤1", "步骤2", "步骤3"],
      "resources": ["推荐资源1", "推荐资源2"],
      "estimated_time": "预计学习时长"
    }
  ],
  "learning_plan": [
    {
      "phase": "阶段名称",
      "duration": "时长",
      "goals": ["目标1", "目标2"],
      "activities": ["活动1", "活动2"]
    }
  ],
  "recommended_resources": [
    {
      "type": "book|course|documentation|practice|tool",
      "name": "资源名称",
      "description": "简要描述"
    }
  ],
  "career_advice": "职业发展建议"
}"""


class LLMLearningAdvisor:
    """LLM-based learning advice generator for low-match resumes."""

    def __init__(self, settings: LLMSettings, chat_client: ChatClientProtocol | None = None) -> None:
        self.settings = settings
        self.chat_client = chat_client or OpenAICompatibleChatClient(settings)

    def generate(self, match_data: dict[str, Any]) -> dict[str, Any]:
        score = match_data.get("score", 0)
        gaps = match_data.get("gaps", [])
        learning_path = match_data.get("learning_path", [])
        strengths = match_data.get("strengths", [])
        summary = match_data.get("summary", "")

        user_prompt = f"""人岗匹配结果：
- 匹配得分：{score}/100
- 匹配结论：{summary}
- 候选人优势：{json.dumps(strengths, ensure_ascii=False)[:1000]}
- 技能差距：{json.dumps(gaps, ensure_ascii=False)[:2000]}
- 初步学习路径：{json.dumps(learning_path, ensure_ascii=False)[:1000]}

请根据以上匹配结果，生成详细的学习建议。重点关注差距较大的技能，提供具体可执行的学习步骤。

{LEARNING_ADVICE_SCHEMA}"""

        messages = [
            {"role": "system", "content": LEARNING_ADVICE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = self.chat_client.chat(messages)
            result = json.loads(content.strip())
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")
        except Exception as exc:
            return {
                "state": "error",
                "implementation": "llm_learning_advisor_error",
                "summary": f"学习建议生成失败: {exc}",
                "skill_gaps": [],
                "learning_plan": [],
                "recommended_resources": [],
                "career_advice": "",
                "warnings": [str(exc)],
            }

        return {
            "state": "available",
            "implementation": "llm_learning_advisor",
            "summary": result.get("summary", ""),
            "skill_gaps": list(result.get("skill_gaps", [])),
            "learning_plan": list(result.get("learning_plan", [])),
            "recommended_resources": list(result.get("recommended_resources", [])),
            "career_advice": result.get("career_advice", ""),
            "warnings": [],
        }
