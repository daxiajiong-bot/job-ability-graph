from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .cleaner import clean_text
from .extractor import JDExtractor, RuleBasedExtractor
from .schemas import BatchSummary, SerializedRecord, ValidationResult
from .serializer import serialize_profile
from .validator import validate_profile


@dataclass
class BatchOptions:
    input_path: Path
    output_dir: Path
    force: bool = False
    retry_statuses: set[str] = field(default_factory=set)


OUTPUT_FILES = (
    "profiles.jsonl",
    "validation_results.jsonl",
    "serialized.jsonl",
    "errors.jsonl",
    "cleaned.jsonl",
    "raw_model_outputs.jsonl",
    "summary.json",
)


def _json_dump(record: object) -> str:
    if hasattr(record, "model_dump"):
        record = record.model_dump()
    return json.dumps(record, ensure_ascii=False)


def _append_jsonl(path: Path, record: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json_dump(record) + "\n")


def _load_existing_statuses(output_dir: Path) -> dict[str, str]:
    path = output_dir / "validation_results.jsonl"
    if not path.exists():
        return {}
    statuses: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            statuses[record.get("document_id", "")] = record.get("status", "")
    return statuses


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                yield {"document_id": f"__line_{line_no}", "raw_text": "", "__error__": str(exc)}


def run_batch(options: BatchOptions, extractor: JDExtractor | None = None) -> BatchSummary:
    extractor = extractor or RuleBasedExtractor()
    options.output_dir.mkdir(parents=True, exist_ok=True)
    if options.force:
        for name in OUTPUT_FILES:
            path = options.output_dir / name
            if path.exists():
                path.unlink()
    existing = _load_existing_statuses(options.output_dir)

    summary = BatchSummary(output_dir=str(options.output_dir))
    for record in _iter_jsonl(options.input_path):
        summary.total += 1
        document_id = str(record.get("document_id") or "")

        if record.get("__error__"):
            summary.failed += 1
            _append_jsonl(options.output_dir / "errors.jsonl", {"document_id": document_id, "error": record["__error__"]})
            continue

        previous_status = existing.get(document_id)
        if previous_status and not options.force:
            if not options.retry_statuses or previous_status not in options.retry_statuses:
                summary.skipped += 1
                continue

        raw_text = str(record.get("raw_text") or "")
        try:
            cleaned = clean_text(raw_text)
            profile = extractor.extract(document_id, raw_text)
            validation = validate_profile(profile, raw_text=raw_text, cleaned_text=cleaned)
            serialized_text = serialize_profile(validation.profile) if validation.profile else ""

            _append_jsonl(options.output_dir / "cleaned.jsonl", {"document_id": document_id, "cleaned_text": cleaned})
            _append_jsonl(
                options.output_dir / "raw_model_outputs.jsonl",
                {"document_id": document_id, "extractor": extractor.__class__.__name__, "raw_output": profile.model_dump()},
            )
            if validation.profile:
                _append_jsonl(options.output_dir / "profiles.jsonl", validation.profile)
            _append_jsonl(options.output_dir / "validation_results.jsonl", validation)
            _append_jsonl(
                options.output_dir / "serialized.jsonl",
                SerializedRecord(document_id=document_id, status=validation.status, serialized_text=serialized_text),
            )

            if validation.status == "valid":
                summary.valid += 1
            elif validation.status == "invalid":
                summary.invalid += 1
            elif validation.status == "needs_review":
                summary.needs_review += 1
        except Exception as exc:
            summary.failed += 1
            _append_jsonl(options.output_dir / "errors.jsonl", {"document_id": document_id, "error": repr(exc)})

    with (options.output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        handle.write(_json_dump(summary) + "\n")
    return summary
