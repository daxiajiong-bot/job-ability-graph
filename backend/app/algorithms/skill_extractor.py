"""Rule-based skill mention extraction from evidence snippets."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from backend.app.algorithms.common import SkillMention
from backend.app.algorithms.skill_catalog import ALIAS_TO_SKILL, SKILL_CATALOG
from backend.app.algorithms.text_rules import local_evidence_clause


def _looks_like_latin_alias(alias: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9+#.-]", alias))


def _find_aliases(text: str) -> List[Tuple[str, str, int]]:
    matches: List[Tuple[str, str, int]] = []
    seen = set()
    for alias, standard_name in sorted(ALIAS_TO_SKILL.items(), key=lambda item: len(item[0]), reverse=True):
        if not alias:
            continue
        if _looks_like_latin_alias(alias):
            pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", re.IGNORECASE)
            iterator = pattern.finditer(text)
        else:
            iterator = re.finditer(re.escape(alias), text)
        for match in iterator:
            key = (standard_name, match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            matches.append((match.group(0), standard_name, match.start()))
    return sorted(matches, key=lambda item: item[2])


def extract_skill_mentions(evidence_items: Sequence[Dict[str, Any]], source_type: str) -> List[SkillMention]:
    mentions: List[SkillMention] = []
    for evidence in evidence_items:
        text = evidence["text"]
        for alias, _standard, offset in _find_aliases(text):
            local_context = local_evidence_clause(text, offset, offset + len(alias))
            mentions.append(
                SkillMention(
                    mention_id=f"{source_type}_m{len(mentions) + 1:03d}",
                    raw_text=alias,
                    source_type=source_type,
                    source_section=evidence["section"],
                    evidence_text=local_context or text,
                    evidence_id=evidence.get("evidence_id"),
                    position=evidence.get("position", 0) + offset,
                    confidence=0.95 if alias in SKILL_CATALOG else 0.88,
                )
            )
    return mentions
