"""Human-review queue export and non-destructive decision import."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ValidationError

from .io_utils import read_jsonl, sha256_file, write_jsonl
from .schemas import EmergingRole, JobSkillUpdate, KGLinkDelta, ReviewDecision


REVIEW_COLUMNS = [
    "object_type",
    "object_id",
    "source_file",
    "source_sha256",
    "current_status",
    "decision",
    "canonical_title",
    "reviewer",
    "reviewed_at",
    "notes",
    "edits_json",
]

_EDITABLE_FIELDS: dict[str, set[str]] = {
    "emerging_role": {
        "canonical_title",
        "aliases",
        "core_responsibilities",
        "required_skills",
        "preferred_skills",
        "typical_industry_scenarios",
        "industries",
        "regions",
        "explanation",
    },
    "job_skill_update": {"canonical_role", "explanation"},
    "ability_mapping": {"properties"},
}


def _load_models(path: str | Path | None, model: type[BaseModel]) -> list[BaseModel]:
    if path is None:
        return []
    return [model.model_validate(row) for row in read_jsonl(path)]


def _atomic_write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in REVIEW_COLUMNS})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _queue_row(
    *,
    object_type: str,
    object_id: str,
    source: Path,
    current_status: str,
    canonical_title: str,
) -> dict[str, str]:
    return {
        "object_type": object_type,
        "object_id": object_id,
        "source_file": source.name,
        "source_sha256": sha256_file(source),
        "current_status": current_status,
        "decision": "",
        "canonical_title": canonical_title,
        "reviewer": "",
        "reviewed_at": "",
        "notes": "",
        "edits_json": "{}",
    }


def export_review_queue(
    output_path: str | Path,
    *,
    emerging_roles_path: str | Path | None = None,
    job_skill_updates_path: str | Path | None = None,
    kg_link_delta_path: str | Path | None = None,
) -> int:
    """Export a stable CSV queue without modifying any source artifact."""

    rows: list[dict[str, str]] = []
    if emerging_roles_path is not None:
        source = Path(emerging_roles_path)
        for value in _load_models(source, EmergingRole):
            role = EmergingRole.model_validate(value)
            rows.append(
                _queue_row(
                    object_type="emerging_role",
                    object_id=role.role_id,
                    source=source,
                    current_status=role.status,
                    canonical_title=role.canonical_title,
                )
            )
    if job_skill_updates_path is not None:
        source = Path(job_skill_updates_path)
        for value in _load_models(source, JobSkillUpdate):
            update = JobSkillUpdate.model_validate(value)
            rows.append(
                _queue_row(
                    object_type="job_skill_update",
                    object_id=update.update_id,
                    source=source,
                    current_status=update.status,
                    canonical_title=update.canonical_role,
                )
            )
    if kg_link_delta_path is not None:
        source = Path(kg_link_delta_path)
        for value in _load_models(source, KGLinkDelta):
            delta = KGLinkDelta.model_validate(value)
            title = str(
                delta.properties.get("canonical_name")
                or delta.properties.get("name")
                or delta.source_id
            )
            rows.append(
                _queue_row(
                    object_type="ability_mapping",
                    object_id=delta.delta_id,
                    source=source,
                    current_status=delta.resolution_status,
                    canonical_title=title,
                )
            )
    keys = [(row["object_type"], row["object_id"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("review queue contains duplicate object type/id pairs")
    rows.sort(key=lambda row: (row["object_type"], row["object_id"]))
    _atomic_write_csv(Path(output_path), rows)
    return len(rows)


def _read_review_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{source}: missing CSV header")
        missing = sorted(set(REVIEW_COLUMNS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{source}: missing review columns: {missing}")
        return [{key: str(value or "") for key, value in row.items()} for row in reader]


def _artifact_map(
    path: str | Path | None, model: type[BaseModel], id_field: str
) -> tuple[Path | None, list[BaseModel], dict[str, BaseModel]]:
    if path is None:
        return None, [], {}
    source = Path(path)
    values = _load_models(source, model)
    mapping: dict[str, BaseModel] = {}
    for item in values:
        object_id = str(getattr(item, id_field))
        if object_id in mapping:
            raise ValueError(f"{source}: duplicate object id {object_id!r}")
        mapping[object_id] = item
    return source, values, mapping


def _parse_edits(row: Mapping[str, str]) -> dict[str, Any]:
    raw = row.get("edits_json", "").strip() or "{}"
    try:
        edits = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{row.get('object_type')}/{row.get('object_id')}: invalid edits_json: {exc}"
        ) from exc
    if not isinstance(edits, dict):
        raise ValueError(
            f"{row.get('object_type')}/{row.get('object_id')}: edits_json must be an object"
        )
    object_type = row["object_type"]
    unknown = sorted(set(edits) - _EDITABLE_FIELDS[object_type])
    if unknown:
        raise ValueError(
            f"{object_type}/{row['object_id']}: protected or unknown edit fields: {unknown}"
        )
    title = row.get("canonical_title", "").strip()
    if title:
        title_field = "canonical_role" if object_type == "job_skill_update" else "canonical_title"
        if object_type != "ability_mapping":
            edits[title_field] = title
    return edits


def _validate_source_snapshot(row: Mapping[str, str], source: Path) -> None:
    if row.get("source_file") and row["source_file"] != source.name:
        raise ValueError(
            f"{row['object_type']}/{row['object_id']}: expected source {row['source_file']!r}, "
            f"got {source.name!r}"
        )
    expected = row.get("source_sha256", "").strip()
    if expected and sha256_file(source) != expected:
        raise ValueError(
            f"{row['object_type']}/{row['object_id']}: source changed after review export"
        )


def _reviewed_at(value: str) -> datetime:
    if not value.strip():
        return datetime.now(timezone.utc)
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"invalid reviewed_at {value!r}; use ISO-8601") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ensure_distinct_output(output: Path, source: Path | None) -> None:
    if source is not None and output.resolve() == source.resolve():
        raise ValueError(f"review import refuses to overwrite original artifact {source}")


def import_review_queue(
    review_csv_path: str | Path,
    output_dir: str | Path,
    *,
    emerging_roles_path: str | Path | None = None,
    job_skill_updates_path: str | Path | None = None,
    kg_link_delta_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply reviewed rows to copies and emit a separate decision audit log."""

    role_source, roles, role_map = _artifact_map(emerging_roles_path, EmergingRole, "role_id")
    update_source, updates, update_map = _artifact_map(
        job_skill_updates_path, JobSkillUpdate, "update_id"
    )
    delta_source, deltas, delta_map = _artifact_map(kg_link_delta_path, KGLinkDelta, "delta_id")
    sources = {
        "emerging_role": role_source,
        "job_skill_update": update_source,
        "ability_mapping": delta_source,
    }
    objects = {
        "emerging_role": role_map,
        "job_skill_update": update_map,
        "ability_mapping": delta_map,
    }
    models: dict[str, type[BaseModel]] = {
        "emerging_role": EmergingRole,
        "job_skill_update": JobSkillUpdate,
        "ability_mapping": KGLinkDelta,
    }

    decisions: list[ReviewDecision] = []
    reviewed: set[tuple[str, str]] = set()
    rows = _read_review_csv(review_csv_path)
    for row in rows:
        decision_value = row.get("decision", "").strip()
        if not decision_value:
            continue
        object_type = row.get("object_type", "").strip()
        object_id = row.get("object_id", "").strip()
        if object_type not in objects:
            raise ValueError(f"unknown review object_type {object_type!r}")
        key = (object_type, object_id)
        if key in reviewed:
            raise ValueError(f"duplicate review decision for {object_type}/{object_id}")
        reviewed.add(key)
        source = sources[object_type]
        if source is None:
            raise ValueError(f"review queue references {object_type}, but no artifact path was supplied")
        _validate_source_snapshot(row, source)
        item = objects[object_type].get(object_id)
        if item is None:
            raise ValueError(f"review queue references unknown {object_type}/{object_id}")
        reviewer = row.get("reviewer", "").strip()
        if not reviewer:
            raise ValueError(f"{object_type}/{object_id}: reviewer is required")
        edits = _parse_edits(row)
        data = item.model_dump(mode="python")
        data.update(edits)
        if object_type in {"emerging_role", "job_skill_update"}:
            data["status"] = decision_value
        else:
            properties = dict(data.get("properties", {}))
            properties["review_status"] = decision_value
            properties["reviewer"] = reviewer
            properties["reviewed_at"] = _reviewed_at(row.get("reviewed_at", "")).isoformat()
            if row.get("notes", "").strip():
                properties["review_notes"] = row["notes"].strip()
            data["properties"] = properties
            if decision_value == "approved" and data["resolution_status"] == "review_candidate":
                data["resolution_status"] = "curated_alias"
            elif decision_value == "rejected":
                data["resolution_status"] = "unresolved"
        try:
            objects[object_type][object_id] = models[object_type].model_validate(data)
            decision = ReviewDecision(
                object_type=object_type,
                object_id=object_id,
                decision=decision_value,
                canonical_title=(row.get("canonical_title", "").strip() or None),
                reviewer=reviewer,
                reviewed_at=_reviewed_at(row.get("reviewed_at", "")),
                notes=(row.get("notes", "").strip() or None),
            )
        except ValidationError as exc:
            raise ValueError(f"invalid review for {object_type}/{object_id}: {exc}") from exc
        decisions.append(decision)

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    if role_source is not None:
        path = target / "emerging_roles.jsonl"
        _ensure_distinct_output(path, role_source)
        write_jsonl(path, [role_map[role.role_id] for role in roles])
        outputs["emerging_roles"] = str(path)
    if update_source is not None:
        path = target / "job_skill_updates.jsonl"
        _ensure_distinct_output(path, update_source)
        write_jsonl(path, [update_map[update.update_id] for update in updates])
        outputs["job_skill_updates"] = str(path)
    if delta_source is not None:
        path = target / "kg_link_delta.jsonl"
        _ensure_distinct_output(path, delta_source)
        write_jsonl(path, [delta_map[delta.delta_id] for delta in deltas])
        outputs["kg_link_delta"] = str(path)
    decision_path = target / "review_decisions.jsonl"
    write_jsonl(decision_path, decisions)
    outputs["review_decisions"] = str(decision_path)
    return {"reviewed": len(decisions), "skipped": len(rows) - len(decisions), "outputs": outputs}


# CLI-friendly aliases.
review_export = export_review_queue
review_import = import_review_queue


__all__ = [
    "REVIEW_COLUMNS",
    "export_review_queue",
    "import_review_queue",
    "review_export",
    "review_import",
]
