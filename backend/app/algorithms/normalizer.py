"""Text normalization and skill name normalization."""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, List, Optional, Sequence

from backend.app.algorithms.common import NormalizedSkill, SkillMention
from backend.app.algorithms.skill_catalog import ALIAS_TO_SKILL, SKILL_CATALOG


def normalize_text(text: str) -> str:
    text = text or ""
    translate_map = str.maketrans(
        {
            "：": ":",
            "；": ";",
            "，": ",",
            "（": "(",
            "）": ")",
            "【": "[",
            "】": "]",
            "—": "-",
            "–": "-",
            "－": "-",
        }
    )
    text = text.translate(translate_map)
    text = re.sub(r"[•●◆■▪▫◦]", "\n", text)
    text = re.sub(r"\t+", " ", text)
    text = re.sub(r"[ \u3000]+", " ", text)
    text = re.sub(r"(?<!\d)(?:^|\s)(\d{1,2}[、.)])\s*", "\n", text)
    text = re.sub(r"(?:^|\s)([一二三四五六七八九十]+[、.)])\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclasses.dataclass
class SkillNormalizerOutput:
    normalized_skills: List[NormalizedSkill]
    unmatched_mentions: List[SkillMention]
    normalization_logs: List[str]


class SkillNormalizer:
    def normalize(self, skill_mentions: Sequence[SkillMention]) -> SkillNormalizerOutput:
        grouped: Dict[str, Dict[str, Any]] = {}
        unmatched: List[SkillMention] = []
        logs: List[str] = []

        for mention in skill_mentions:
            standard_name = self._normalize_name(mention.raw_text)
            if not standard_name:
                unmatched.append(mention)
                continue
            skill_info = SKILL_CATALOG[standard_name]
            bucket = grouped.setdefault(
                standard_name,
                {
                    "skill_id": skill_info["skill_id"],
                    "name": standard_name,
                    "skill_type": skill_info["skill_type"],
                    "aliases": set(),
                    "evidence_refs": [],
                    "confidences": [],
                    "relation_type": "exact",
                },
            )
            bucket["aliases"].add(mention.raw_text)
            bucket["evidence_refs"].append(mention.mention_id)
            bucket["confidences"].append(mention.confidence)
            if mention.raw_text != standard_name:
                bucket["relation_type"] = "alias"
                logs.append(f"{mention.raw_text} -> {standard_name}")

        normalized = [
            NormalizedSkill(
                skill_id=bucket["skill_id"],
                name=bucket["name"],
                skill_type=bucket["skill_type"],
                aliases=sorted(bucket["aliases"]),
                relation_type=bucket["relation_type"],
                evidence_refs=bucket["evidence_refs"],
                confidence=round(sum(bucket["confidences"]) / max(1, len(bucket["confidences"])), 3),
            )
            for bucket in grouped.values()
        ]
        normalized.sort(key=lambda skill: skill.name)
        return SkillNormalizerOutput(normalized_skills=normalized, unmatched_mentions=unmatched, normalization_logs=logs)

    def _normalize_name(self, raw_text: str) -> Optional[str]:
        if raw_text in ALIAS_TO_SKILL:
            return ALIAS_TO_SKILL[raw_text]
        lowered = raw_text.lower()
        return ALIAS_TO_SKILL.get(lowered)
