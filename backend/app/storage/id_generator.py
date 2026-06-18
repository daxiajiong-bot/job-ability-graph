"""Stable readable IDs for demo documents, graph nodes, and artifacts."""

from __future__ import annotations

import hashlib
import re
from typing import Any


MAX_SLUG_LENGTH = 36


def _stable_hash(value: Any, length: int = 10) -> str:
    text = str(value or "")
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def _slug(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_+#.-]+", "", text)
    text = re.sub(r"_+", "_", text).strip("_.-")
    if not text:
        text = fallback
    return text[:MAX_SLUG_LENGTH].strip("_.-") or fallback


def _stable_prefixed_id(prefix: str, value: Any, fallback: str) -> str:
    return f"{prefix}_{_slug(value, fallback)}_{_stable_hash(value)}"


def make_doc_id(doc_type: str, text_or_name: str) -> str:
    normalized_type = _slug(doc_type, "doc")
    return _stable_prefixed_id(normalized_type, text_or_name, normalized_type)


def make_skill_id(skill_name: str) -> str:
    return _stable_prefixed_id("skill", skill_name, "skill")


def make_position_id(position_name: str) -> str:
    return _stable_prefixed_id("position", position_name, "position")


def make_candidate_id(candidate_name_or_resume_id: str) -> str:
    return _stable_prefixed_id("candidate", candidate_name_or_resume_id, "candidate")


def make_evidence_id(source_doc_id: str, index: int) -> str:
    safe_doc_id = _slug(source_doc_id, "doc")
    return f"evidence_{safe_doc_id}_{int(index):03d}"


def make_match_id(jd_id: str, resume_id: str) -> str:
    left = _slug(jd_id, "jd")
    right = _slug(resume_id, "resume")
    return f"match_{left}_{right}_{_stable_hash(f'{jd_id}|{resume_id}')}"
