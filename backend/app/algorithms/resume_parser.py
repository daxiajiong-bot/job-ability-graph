"""Rule-based resume parser."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from backend.app.algorithms.common import ResumeParseResult
from backend.app.algorithms.normalizer import normalize_text
from backend.app.algorithms.skill_extractor import _find_aliases, extract_skill_mentions
from backend.app.algorithms.text_rules import (
    extract_domains,
    extract_education,
    extract_experience_years,
    parse_section_header,
    split_items,
)
from backend.app.algorithms.skill_catalog import RESUME_SECTION_HEADERS


class ResumeParser:
    def parse(
        self,
        resume_text: str,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResumeParseResult:
        text = normalize_text(resume_text)
        sections: Dict[str, List[str]] = defaultdict(list)
        current_section: Optional[str] = None
        warnings: List[str] = []

        for line in split_items(text):
            section, rest = parse_section_header(line, RESUME_SECTION_HEADERS)
            if section:
                current_section = section
                if rest:
                    for item in split_items(rest):
                        sections[section].append(item)
                continue
            effective_section = current_section or self._classify_item(line)
            sections[effective_section].append(line)

        evidence_items: List[Dict[str, Any]] = []
        for section_name in ("target_position", "education", "work_experiences", "projects", "skills", "certificates"):
            for item in sections.get(section_name, []):
                evidence_items.append(
                    {
                        "evidence_id": f"resume_e{len(evidence_items) + 1:03d}",
                        "source_type": "resume",
                        "section": section_name,
                        "text": item,
                        "position": len(evidence_items),
                    }
                )

        raw_mentions = extract_skill_mentions(evidence_items, "resume")
        candidate_id = self._extract_candidate_id(text)
        education = extract_education("\n".join(sections.get("education", []) + [text]), requirement_mode=False)
        experience_years = extract_experience_years(text)
        target_position = self._extract_target_position(sections.get("target_position", []), text)
        domains = extract_domains(text)

        if not sections.get("projects") and not sections.get("work_experiences"):
            warnings.append("未识别到项目或工作经历，技能熟练度可能偏保守")
        if not raw_mentions:
            warnings.append("未识别到技能词表内技能")

        return ResumeParseResult(
            candidate_id=candidate_id,
            education=education,
            experience_years=experience_years,
            target_position=target_position,
            work_experiences=sections.get("work_experiences", []),
            projects=sections.get("projects", []),
            certificates=sections.get("certificates", []),
            domain_experiences=domains,
            raw_skill_mentions=raw_mentions,
            evidence_items=evidence_items,
            parse_warnings=warnings,
        )

    def _classify_item(self, line: str) -> str:
        if any(word in line for word in ("大学", "学院", "本科", "硕士", "博士", "专业", "毕业")):
            return "education"
        if any(word in line for word in ("项目", "系统", "平台", "负责", "参与", "实现", "优化")):
            return "projects"
        if any(word in line for word in ("公司", "工作", "实习", "任职", "工程师")):
            return "work_experiences"
        if any(word in line for word in ("证书", "论文", "专利", "竞赛", "开源")):
            return "certificates"
        if _find_aliases(line):
            return "skills"
        return "basic_info"

    def _extract_candidate_id(self, text: str) -> Optional[str]:
        match = re.search(r"(?:姓名|Name)\s*[:：]\s*([^\n,，;； ]+)", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_target_position(self, target_lines: Sequence[str], text: str) -> Optional[str]:
        if target_lines:
            return target_lines[0].strip()
        match = re.search(r"(?:目标岗位|期望职位|求职意向)\s*[:：]\s*([^\n,，;；]+)", text)
        return match.group(1).strip() if match else None
