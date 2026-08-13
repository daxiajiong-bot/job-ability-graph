from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .io_utils import read_jsonl


EVIDENCE_BEARING_FILES = (
    "trend_features.jsonl",
    "emerging_roles.jsonl",
    "job_skill_updates.jsonl",
    "kg_link_delta.jsonl",
)


def _collect_evidence_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                found.extend(str(candidate) for candidate in item)
            else:
                found.extend(_collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_evidence_ids(item))
    return found


def validate_evidence_references(
    rows: Iterable[dict[str, Any]], known_evidence_ids: set[str]
) -> dict[str, Any]:
    references: list[str] = []
    object_count = 0
    objects_without_evidence = 0
    for row in rows:
        object_count += 1
        current = _collect_evidence_ids(row)
        references.extend(current)
        if not current:
            objects_without_evidence += 1
    unknown = sorted(set(references) - known_evidence_ids)
    return {
        "object_count": object_count,
        "reference_count": len(references),
        "unique_reference_count": len(set(references)),
        "objects_without_evidence": objects_without_evidence,
        "unknown_evidence_ids": unknown,
        "valid_reference_rate": (
            1.0
            if not references
            else (len(references) - sum(1 for value in references if value not in known_evidence_ids))
            / len(references)
        ),
        "status": "valid" if not unknown else "invalid",
    }


def validate_output_directory(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    evidence_path = root / "evidence.jsonl"
    if not evidence_path.is_file():
        raise FileNotFoundError(evidence_path)
    evidence_rows = list(read_jsonl(evidence_path))
    ids = [str(row.get("evidence_id") or "") for row in evidence_rows]
    duplicates = sorted(key for key, value in Counter(ids).items() if key and value > 1)
    checks: dict[str, Any] = {}
    for name in EVIDENCE_BEARING_FILES:
        source = root / name
        checks[name] = (
            validate_evidence_references(read_jsonl(source), set(ids))
            if source.is_file()
            else {"status": "missing"}
        )
    invalid = [name for name, result in checks.items() if result.get("status") == "invalid"]
    return {
        "schema_version": "jobtrend_quality_report_v1",
        "evidence_count": len(ids),
        "duplicate_evidence_ids": duplicates,
        "artifact_checks": checks,
        "status": "valid" if not duplicates and not invalid else "invalid",
    }
