from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable


SCHEMA_VERSION = "embedding_serialized_v1"
EXPECTED_SPLITS = {"train", "validation", "test"}
EXPECTED_SLOTS = {"P1", "P2", "H1"}
EXPECTED_SLOT_LABELS = {
    "P1": (2, "positive"),
    "P2": (2, "positive"),
    "H1": (0, "hard_negative"),
}

_SPACE_RE = re.compile(r"[ \t\u3000]+")
_RESUME_SECTION_RE = re.compile(
    r"^(相关经验|技能|工作经历\d*|项目经历\d*|教育)[：:]"
)
_RESUME_SECTION_ORDER = {
    "相关经验": 0,
    "技能": 1,
    "工作经历": 2,
    "项目经历": 3,
    "教育": 4,
}


def _clean_inline(value: Any) -> str:
    text = str(value or "").replace("\r", "\n")
    text = " ".join(part.strip() for part in text.splitlines() if part.strip())
    return _SPACE_RE.sub(" ", text).strip()


def _clean_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_inline(item)
        if text:
            result.append(text)
    return result


def _numbered_section(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{title}：", *(f"{index}. {text}" for index, text in enumerate(values, 1))]


def serialize_jd(record: dict[str, Any]) -> str:
    """Create model-facing JD text without identifiers or derived labels."""

    job_title = _clean_inline(record.get("job_title"))
    if not job_title:
        raise ValueError("JD is missing job_title")

    requirements = _clean_lines(record.get("requirements"))
    responsibilities = _clean_lines(record.get("responsibilities"))
    education = _clean_inline(record.get("education"))
    experience = _clean_inline(record.get("experience"))

    lines = [f"岗位名称：{job_title}"]
    if education:
        lines.append(f"学历要求：{education}")
    if experience:
        lines.append(f"经验要求：{experience}")

    if requirements:
        # Requirements deliberately precede responsibilities so a later
        # tokenizer truncation preserves non-negotiable constraints first.
        lines.extend(_numbered_section("任职要求", requirements))
        if responsibilities:
            lines.extend(_numbered_section("岗位职责", responsibilities))
        else:
            raw_text = _clean_inline(record.get("jd_text"))
            if raw_text:
                lines.append(f"岗位描述补充：{raw_text}")
    else:
        raw_text = _clean_inline(record.get("jd_text"))
        if not raw_text:
            raise ValueError("JD has neither requirements nor jd_text")
        lines.append(f"岗位原文：{raw_text}")

    return "\n".join(lines)


def _resume_section_key(line: str) -> tuple[int, int]:
    match = _RESUME_SECTION_RE.match(line)
    if not match:
        return (len(_RESUME_SECTION_ORDER), 0)
    label = match.group(1)
    base = re.sub(r"\d+$", "", label)
    suffix = label[len(base) :]
    return (_RESUME_SECTION_ORDER[base], int(suffix or 0))


def serialize_resume(record: dict[str, Any]) -> str:
    """Normalize and reorder the generated resume sections for embedding."""

    raw_text = str(record.get("resume_text") or "").replace("\r", "\n")
    lines = [
        _SPACE_RE.sub(" ", line).strip()
        for line in raw_text.splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError("resume is missing resume_text")

    recognized: list[tuple[int, str]] = []
    unrecognized: list[tuple[int, str]] = []
    for original_index, line in enumerate(lines):
        target = (
            recognized
            if _RESUME_SECTION_RE.match(line)
            else unrecognized
        )
        target.append((original_index, line))

    recognized.sort(
        key=lambda item: (*_resume_section_key(item[1]), item[0])
    )
    ordered = [line for _, line in recognized]
    ordered.extend(line for _, line in unrecognized)
    return "\n".join(ordered)


def _required_id(record: dict[str, Any], key: str, kind: str) -> str:
    value = _clean_inline(record.get(key))
    if not value:
        raise ValueError(f"{kind} is missing {key}")
    return value


def build_embedding_records(
    jds: Iterable[dict[str, Any]],
    resumes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Join the source datasets into corpora, pairs, and query groups."""

    jd_by_id: dict[str, dict[str, Any]] = {}
    jd_records: list[dict[str, Any]] = []
    split_by_jd: dict[str, str] = {}
    for source in jds:
        jd_id = _required_id(source, "jd_id", "JD")
        if jd_id in jd_by_id:
            raise ValueError(f"duplicate jd_id: {jd_id}")
        split = _required_id(source, "split", f"JD {jd_id}")
        if split not in EXPECTED_SPLITS:
            raise ValueError(f"{jd_id}: invalid split {split!r}")
        text = serialize_jd(source)
        jd_by_id[jd_id] = source
        split_by_jd[jd_id] = split
        jd_records.append(
            {
                "id": jd_id,
                "split": split,
                "text": text,
                "metadata": {
                    "job_title": _clean_inline(source.get("job_title")),
                    "education": _clean_inline(source.get("education")) or None,
                    "experience": _clean_inline(source.get("experience")) or None,
                    "job_family_proxy": (
                        _clean_inline(source.get("job_family_proxy")) or None
                    ),
                    "seniority_proxy": (
                        _clean_inline(source.get("seniority_proxy")) or None
                    ),
                },
            }
        )

    resume_by_id: dict[str, dict[str, Any]] = {}
    resume_records: list[dict[str, Any]] = []
    slots_by_jd: defaultdict[str, set[str]] = defaultdict(set)
    for source in resumes:
        resume_id = _required_id(source, "resume_id", "resume")
        if resume_id in resume_by_id:
            raise ValueError(f"duplicate resume_id: {resume_id}")
        jd_id = _required_id(source, "jd_id", f"resume {resume_id}")
        if jd_id not in jd_by_id:
            raise ValueError(f"{resume_id}: unknown jd_id {jd_id}")
        slot = _required_id(source, "slot", f"resume {resume_id}")
        if slot not in EXPECTED_SLOTS:
            raise ValueError(f"{resume_id}: invalid slot {slot!r}")
        split = split_by_jd[jd_id]
        slots_by_jd[jd_id].add(slot)
        text = serialize_resume(source)
        resume_by_id[resume_id] = source
        resume_records.append(
            {
                "id": resume_id,
                "source_jd_id": jd_id,
                "split": split,
                "text": text,
                "metadata": {
                    "slot": slot,
                    "omitted_requirement_ids": list(
                        source.get("omitted_requirement_ids") or []
                    ),
                },
            }
        )

    incomplete_groups = {
        jd_id: sorted(slots)
        for jd_id, slots in slots_by_jd.items()
        if slots != EXPECTED_SLOTS
    }
    missing_resume_groups = sorted(set(jd_by_id) - set(slots_by_jd))
    if incomplete_groups or missing_resume_groups:
        examples = list(sorted(incomplete_groups.items()))[:10]
        raise ValueError(
            "incomplete JD resume triplets: "
            f"groups={examples}, missing={missing_resume_groups[:10]}"
        )

    edge_by_resume_id: dict[str, dict[str, Any]] = {}
    for edge in edges:
        resume_id = _required_id(edge, "resume_id", "edge")
        if resume_id in edge_by_resume_id:
            raise ValueError(f"duplicate edge for resume_id: {resume_id}")
        if resume_id not in resume_by_id:
            raise ValueError(f"edge references unknown resume_id: {resume_id}")
        source_resume = resume_by_id[resume_id]
        jd_id = _required_id(edge, "jd_id", f"edge {resume_id}")
        if jd_id != str(source_resume["jd_id"]):
            raise ValueError(f"{resume_id}: edge/resume jd_id mismatch")
        slot = str(source_resume["slot"])
        expected_relevance, expected_relation = EXPECTED_SLOT_LABELS[slot]
        relevance = edge.get("relevance")
        relation = _clean_inline(edge.get("relation"))
        if relevance != expected_relevance or relation != expected_relation:
            raise ValueError(
                f"{resume_id}: invalid label "
                f"{relevance!r}/{relation!r} for slot {slot}"
            )
        edge_by_resume_id[resume_id] = edge

    resume_ids = set(resume_by_id)
    edge_ids = set(edge_by_resume_id)
    if resume_ids != edge_ids:
        raise ValueError(
            "resume/edge identity mismatch: "
            f"without_edge={sorted(resume_ids - edge_ids)[:10]}, "
            f"without_resume={sorted(edge_ids - resume_ids)[:10]}"
        )

    jd_text_by_id = {row["id"]: row["text"] for row in jd_records}
    resume_text_by_id = {row["id"]: row["text"] for row in resume_records}
    pairs_by_split: dict[str, list[dict[str, Any]]] = {
        split: [] for split in sorted(EXPECTED_SPLITS)
    }
    groups_by_jd: dict[str, dict[str, Any]] = {}
    for jd_id in sorted(jd_by_id):
        groups_by_jd[jd_id] = {
            "query_id": jd_id,
            "split": split_by_jd[jd_id],
            "query_text": jd_text_by_id[jd_id],
            "positives": [],
            "hard_negatives": [],
        }

    for resume_record in sorted(resume_records, key=lambda row: row["id"]):
        resume_id = str(resume_record["id"])
        jd_id = str(resume_record["source_jd_id"])
        split = str(resume_record["split"])
        edge = edge_by_resume_id[resume_id]
        pair = {
            "query_id": jd_id,
            "document_id": resume_id,
            "split": split,
            "relevance": int(edge["relevance"]),
            "relation": str(edge["relation"]),
            "query_text": jd_text_by_id[jd_id],
            "document_text": resume_text_by_id[resume_id],
        }
        pairs_by_split[split].append(pair)
        grouped_document = {
            "document_id": resume_id,
            "document_text": resume_text_by_id[resume_id],
            "relevance": int(edge["relevance"]),
        }
        target = (
            groups_by_jd[jd_id]["positives"]
            if edge["relation"] == "positive"
            else groups_by_jd[jd_id]["hard_negatives"]
        )
        target.append(grouped_document)

    groups_by_split: dict[str, list[dict[str, Any]]] = {
        split: [] for split in sorted(EXPECTED_SPLITS)
    }
    for jd_id in sorted(groups_by_jd):
        group = groups_by_jd[jd_id]
        if (
            len(group["positives"]) != 2
            or len(group["hard_negatives"]) != 1
        ):
            raise ValueError(f"{jd_id}: invalid grouped label distribution")
        groups_by_split[group["split"]].append(group)

    jd_records.sort(key=lambda row: row["id"])
    resume_records.sort(key=lambda row: row["id"])
    return {
        "jds": jd_records,
        "resumes": resume_records,
        "pairs_by_split": pairs_by_split,
        "groups_by_split": groups_by_split,
        "counts": {
            "jds": len(jd_records),
            "resumes": len(resume_records),
            "pairs": sum(len(rows) for rows in pairs_by_split.values()),
            "jds_by_split": dict(Counter(split_by_jd.values())),
            "resumes_by_split": dict(
                Counter(str(row["split"]) for row in resume_records)
            ),
            "relations": dict(
                Counter(
                    str(edge["relation"])
                    for edge in edge_by_resume_id.values()
                )
            ),
        },
    }
