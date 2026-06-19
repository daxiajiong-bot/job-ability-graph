"""Rule-based JD parser."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.app.algorithms.common import JDParseResult
from backend.app.algorithms.normalizer import normalize_text
from backend.app.algorithms.skill_extractor import extract_skill_mentions
from backend.app.algorithms.text_rules import (
    extract_domains,
    extract_education,
    extract_min_year_requirement,
    infer_job_category,
    parse_section_header,
    split_items,
)
from backend.app.algorithms.skill_catalog import (
    DOMAIN_KEYWORDS,
    JD_SECTION_HEADERS,
    JD_VERBS,
    PREFERRED_WORDS,
    REQUIREMENT_WORDS,
)


class JDParser:
    def parse(self, jd_text: str, source_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> JDParseResult:
        text = normalize_text(jd_text)
        warnings: List[str] = []
        sections: Dict[str, List[str]] = defaultdict(list)
        current_section: Optional[str] = None
        job_title = ""

        for line in split_items(text):
            section, rest = parse_section_header(line, JD_SECTION_HEADERS)
            if section:
                current_section = section
                if section == "job_title":
                    if rest:
                        job_title = rest
                        sections["job_title"].append(rest)
                    continue
                if rest:
                    for item in split_items(rest):
                        sections[section].append(item)
                continue

            effective_section = current_section or self._classify_item(line)
            if effective_section == "job_title":
                if not job_title:
                    job_title = line
                sections["job_title"].append(line)
            elif effective_section == "education":
                sections["requirements"].append(line)
                sections["education"].append(line)
            elif effective_section == "experience":
                sections["requirements"].append(line)
                sections["experience"].append(line)
            elif effective_section == "domain":
                sections["requirements"].append(line)
                sections["domain"].append(line)
            else:
                sections[effective_section].append(line)

        if not job_title:
            job_title = self._infer_title(text)
        if not job_title:
            job_title = "未识别岗位"
            warnings.append("未能识别明确岗位名称")

        responsibilities = sections.get("responsibilities", [])
        requirements = sections.get("requirements", [])
        preferred = sections.get("preferred", [])

        evidence_items: List[Dict[str, Any]] = []
        for section_name, items in (
            ("job_title", sections.get("job_title", []) or ([job_title] if job_title != "未识别岗位" else [])),
            ("responsibilities", responsibilities),
            ("requirements", requirements),
            ("preferred", preferred),
        ):
            for item in items:
                evidence_items.append(
                    {
                        "evidence_id": f"jd_e{len(evidence_items) + 1:03d}",
                        "source_type": "jd",
                        "section": section_name,
                        "text": item,
                        "position": len(evidence_items),
                    }
                )

        raw_mentions = extract_skill_mentions(evidence_items, "jd")
        education_requirement = extract_education("\n".join(requirements + sections.get("education", [])), requirement_mode=True)
        experience_requirement = extract_min_year_requirement("\n".join(requirements + sections.get("experience", [])))
        domains = extract_domains(text)
        job_category = infer_job_category(text, job_title)

        if not responsibilities:
            warnings.append("未识别到显式岗位职责，已使用规则兜底")
        if not requirements:
            warnings.append("未识别到显式任职要求，已使用规则兜底")

        return JDParseResult(
            job_title=job_title,
            job_category=job_category,
            responsibilities=responsibilities,
            requirements=requirements,
            preferred=preferred,
            education_requirement=education_requirement,
            experience_requirement=experience_requirement,
            domain_requirement=domains,
            raw_skill_mentions=raw_mentions,
            evidence_items=evidence_items,
            parse_warnings=warnings,
        )

    def _classify_item(self, line: str) -> str:
        lowered = line.lower()
        if any(word.lower() in lowered for word in PREFERRED_WORDS):
            return "preferred"
        if any(word in line for word in ("学历", "本科", "硕士", "博士", "大专", "专科")):
            return "education"
        if extract_min_year_requirement(line) is not None or "经验" in line:
            return "experience"
        if any(domain.lower() in lowered for domain in DOMAIN_KEYWORDS):
            return "domain"
        if any(word in line for word in REQUIREMENT_WORDS):
            return "requirements"
        if any(word in line for word in JD_VERBS):
            return "responsibilities"
        return "requirements"

    def _infer_title(self, text: str) -> str:
        explicit = re.search(r"(?:岗位|职位|招聘职位|Job Title)\s*[:：]\s*([^\n。；;]+)", text, flags=re.IGNORECASE)
        if explicit:
            return explicit.group(1).strip()
        for line in split_items(text)[:3]:
            if len(line) <= 32 and any(keyword in line for keyword in ("工程师", "开发", "算法", "经理", "专家", "专员", "分析师")):
                return line
        return ""
