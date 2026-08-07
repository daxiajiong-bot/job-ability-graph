from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .extractor import PREFERRED_HINTS, REQUIRED_HINTS, SKILL_PATTERNS
from .schemas import JDProfile, Skill
from .serializer import serialize_profile
from .validator import validate_profile


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).lower()


def _clean_surface(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_evidence_units(raw_text: str) -> list[str]:
    units: list[str] = []
    for line in (raw_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[。；;.!?？])\s*", line)
        for part in parts:
            part = part.strip()
            if part:
                units.append(part)
    return units


def infer_skill_level(evidence: str) -> str:
    lowered = evidence.lower()
    if any(hint.lower() in lowered for hint in PREFERRED_HINTS):
        return "preferred"
    if any(hint.lower() in lowered for hint in REQUIRED_HINTS):
        return "required"
    return "mentioned"


class LocalRAGIndex:
    """A local retrieval index over extracted skill surfaces and evidence examples.

    It does not generate unsupported facts. Retrieved candidates are only accepted
    when the candidate surface appears in the target JD raw_text.
    """

    def __init__(self, skill_terms: dict[str, dict[str, Any]]) -> None:
        self.skill_terms = skill_terms

    @classmethod
    def from_profiles(cls, profiles: list[dict[str, Any]], max_examples_per_skill: int = 8) -> "LocalRAGIndex":
        skill_terms: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            for skill in profile.get("skills") or []:
                name = _clean_surface(str(skill.get("name") or ""))
                evidence = _clean_surface(str(skill.get("evidence") or ""))
                level = str(skill.get("level") or "")
                if not name:
                    continue
                key = _compact(name)
                item = skill_terms.setdefault(
                    key,
                    {
                        "name": name,
                        "count": 0,
                        "levels": Counter(),
                        "examples": [],
                    },
                )
                item["count"] += 1
                item["levels"][level] += 1
                if len(item["examples"]) < max_examples_per_skill:
                    item["examples"].append(
                        {
                            "document_id": profile.get("document_id"),
                            "title": profile.get("title"),
                            "level": level,
                            "evidence": evidence,
                        }
                    )

        for item in skill_terms.values():
            item["levels"] = dict(item["levels"])
        return cls(skill_terms)

    def retrieve_terms_in_text(self, raw_text: str) -> list[dict[str, Any]]:
        compact_text = _compact(raw_text)
        hits: list[dict[str, Any]] = []
        for key, item in self.skill_terms.items():
            if key and key in compact_text:
                hits.append(item)
        hits.sort(key=lambda row: (-int(row.get("count", 0)), row.get("name", "")))
        return hits

    def to_jsonable(self) -> dict[str, Any]:
        top_terms = sorted(self.skill_terms.values(), key=lambda row: (-int(row["count"]), row["name"]))
        return {
            "term_count": len(self.skill_terms),
            "top_terms": top_terms[:100],
        }


def _pattern_candidates(raw_text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in SKILL_PATTERNS:
        for match in re.finditer(pattern, raw_text or "", flags=re.I):
            surface = _clean_surface(match.group(0))
            if surface:
                candidates.append(surface)
    return candidates


def _find_evidence(raw_text: str, term: str) -> str | None:
    compact_term = _compact(term)
    for unit in split_evidence_units(raw_text):
        if compact_term and compact_term in _compact(unit):
            return unit
    return None


def augment_profile_with_rag(profile: dict[str, Any], index: LocalRAGIndex, max_additions: int = 20) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_text = profile.get("raw_text") or ""
    existing_keys = {_compact(skill.get("name")) for skill in profile.get("skills") or [] if skill.get("name")}
    retrieved = index.retrieve_terms_in_text(raw_text)
    candidate_terms: dict[str, dict[str, Any]] = {}

    for item in retrieved:
        name = str(item.get("name") or "").strip()
        key = _compact(name)
        if key and key not in existing_keys:
            candidate_terms[key] = {"name": name, "source": "retrieved_skill_index", "retrieval_count": item.get("count", 0)}

    for term in _pattern_candidates(raw_text):
        key = _compact(term)
        if key and key not in existing_keys:
            candidate_terms.setdefault(key, {"name": term, "source": "pattern_candidate", "retrieval_count": 0})

    additions: list[dict[str, Any]] = []
    for key, candidate in sorted(candidate_terms.items(), key=lambda row: (-int(row[1].get("retrieval_count", 0)), row[1]["name"])):
        if len(additions) >= max_additions:
            break
        evidence = _find_evidence(raw_text, candidate["name"])
        if not evidence:
            continue
        level = infer_skill_level(evidence)
        additions.append(
            {
                "name": candidate["name"],
                "level": level,
                "evidence": evidence,
                "rag_source": candidate["source"],
                "retrieval_count": candidate.get("retrieval_count", 0),
            }
        )
        existing_keys.add(key)

    if not additions:
        return profile, []

    augmented = dict(profile)
    skills = list(profile.get("skills") or [])
    for item in additions:
        skills.append({"name": item["name"], "level": item["level"], "evidence": item["evidence"]})
    augmented["skills"] = skills
    return augmented, additions


def run_rag_augmentation(profiles_path: Path, output_dir: Path, max_additions: int = 20) -> dict[str, Any]:
    profiles = _read_jsonl(profiles_path)
    index = LocalRAGIndex.from_profiles(profiles)
    output_dir.mkdir(parents=True, exist_ok=True)

    augmented_profiles: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    serialized_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    added_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    validation_counter: Counter[str] = Counter()

    for profile in profiles:
        document_id = profile.get("document_id") or ""
        try:
            augmented, additions = augment_profile_with_rag(profile, index, max_additions=max_additions)
            validated = validate_profile(augmented, raw_text=augmented.get("raw_text"), cleaned_text=augmented.get("raw_text"))
            validation_counter[validated.status] += 1
            validation_rows.append(validated.model_dump())
            if validated.profile:
                profile_dict = validated.profile.model_dump()
                augmented_profiles.append(profile_dict)
                serialized_rows.append(
                    {
                        "document_id": document_id,
                        "status": validated.status,
                        "serialized_text": serialize_profile(validated.profile),
                    }
                )
            for item in additions:
                added_counter[item["name"]] += 1
                source_counter[item["rag_source"]] += 1
            audit_rows.append(
                {
                    "document_id": document_id,
                    "title": profile.get("title"),
                    "added_skill_count": len(additions),
                    "added_skills": additions,
                }
            )
        except Exception as exc:
            errors.append({"document_id": document_id, "error": repr(exc)})

    original_skill_mentions = sum(len(profile.get("skills") or []) for profile in profiles)
    augmented_skill_mentions = sum(len(profile.get("skills") or []) for profile in augmented_profiles)
    docs_with_additions = sum(1 for row in audit_rows if row["added_skill_count"] > 0)

    summary = {
        "schema_version": "jd_rag_augmentation_v1",
        "source_profile_count": len(profiles),
        "augmented_profile_count": len(augmented_profiles),
        "validation_status_counts": dict(validation_counter),
        "original_skill_mentions": original_skill_mentions,
        "augmented_skill_mentions": augmented_skill_mentions,
        "added_skill_mentions": augmented_skill_mentions - original_skill_mentions,
        "docs_with_additions": docs_with_additions,
        "docs_with_additions_ratio": round(docs_with_additions / len(profiles), 4) if profiles else 0,
        "max_additions_per_doc": max_additions,
        "added_skill_source_counts": dict(source_counter),
        "top_added_skills": [{"name": name, "count": count} for name, count in added_counter.most_common(50)],
        "error_count": len(errors),
        "rag_policy": {
            "mode": "local_retrieval_with_evidence_gate",
            "facts_added_only_if_surface_is_found_in_current_raw_text": True,
            "external_llm_api_used": False,
            "external_vector_db_used": False,
        },
    }

    _write_jsonl(output_dir / "profiles.jsonl", augmented_profiles)
    _write_jsonl(output_dir / "validation_results.jsonl", validation_rows)
    _write_jsonl(output_dir / "serialized.jsonl", serialized_rows)
    _write_jsonl(output_dir / "rag_added_skills.jsonl", audit_rows)
    _write_jsonl(output_dir / "errors.jsonl", errors)
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "retrieval_index_summary.json", index.to_jsonable())
    return summary

