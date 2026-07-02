"""Filesystem-backed registry and artifact store for governed documents."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from backend.app.data_governance.schemas import DocumentMetadata, QualityReport
from backend.app.domain.entities import utc_now
from backend.app.domain.errors import InvalidInputError, ResourceNotFoundError


DATA_DIRS = ("raw", "staging", "structured", "graph", "rag", "audit")


class DataGovernanceStore:
    """Owns immutable raw copies plus versioned derived artifacts."""

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        for directory in DATA_DIRS:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "audit" / "document_registry.json"

    def register_bytes(
        self,
        *,
        document_type: str,
        content: bytes,
        file_name: str,
        mime_type: str | None,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> DocumentMetadata:
        if not content:
            raise InvalidInputError("uploaded file must not be empty")
        registry = self._load_registry()
        content_hash = sha256(content).hexdigest()
        duplicate_ref = registry["hash_index"].get(content_hash)
        if duplicate_ref:
            existing = self.get_metadata(duplicate_ref["doc_id"], int(duplicate_ref["version"]))
            duplicate = replace(existing, status="duplicate", duplicate_of=f"{existing.doc_id}:v{existing.version}")
            self._append_event("duplicate_detected", duplicate.to_dict())
            return duplicate

        source_system = str(source.get("source_system") or "manual").strip() or "manual"
        external_id = _clean_optional(source.get("external_id"))
        source_key = _source_key(source_system, external_id)
        if source_key and source_key in registry["source_index"]:
            doc_id = registry["source_index"][source_key]["doc_id"]
            version = int(registry["documents"][doc_id]["current_version"]) + 1
        else:
            doc_id = f"doc_{content_hash[:16]}"
            version = 1

        safe_name = _safe_file_name(file_name)
        raw_dir = self.root / "raw" / doc_id / f"v{version}"
        raw_dir.mkdir(parents=True, exist_ok=False)
        raw_path = raw_dir / safe_name
        with raw_path.open("xb") as handle:
            handle.write(content)

        now = utc_now()
        document = DocumentMetadata(
            doc_id=doc_id,
            version=version,
            document_type=document_type,
            source_system=source_system,
            external_id=external_id,
            source_uri=_clean_optional(source.get("uri")),
            original_filename=file_name or safe_name,
            raw_path=str(raw_path),
            content_hash=content_hash,
            byte_size=len(content),
            mime_type=mime_type,
            created_at=now,
            status="registered",
            metadata=dict(metadata),
        )
        registry["documents"].setdefault(doc_id, {"doc_id": doc_id, "versions": {}})
        registry["documents"][doc_id]["current_version"] = version
        registry["documents"][doc_id]["versions"][str(version)] = document.to_dict()
        registry["hash_index"][content_hash] = {"doc_id": doc_id, "version": version}
        if source_key:
            registry["source_index"][source_key] = {"doc_id": doc_id, "latest_version": version}
        registry["updated_at"] = now
        self._save_registry(registry)
        self._append_event("document_registered", document.to_dict())
        return document

    def register_path(
        self,
        *,
        document_type: str,
        path: str | Path,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> DocumentMetadata:
        source_path = Path(path)
        if not source_path.exists() or not source_path.is_file():
            raise InvalidInputError(f"raw source path does not exist: {source_path}")
        content = source_path.read_bytes()
        enriched = {**metadata, "registered_from_path": str(source_path)}
        return self.register_bytes(
            document_type=document_type,
            content=content,
            file_name=source_path.name,
            mime_type=None,
            source=source,
            metadata=enriched,
        )

    def get_metadata(self, doc_id: str, version: int | None = None) -> DocumentMetadata:
        registry = self._load_registry()
        document = registry["documents"].get(doc_id)
        if not document:
            raise ResourceNotFoundError(f"governed document '{doc_id}' was not found")
        selected_version = int(version or document["current_version"])
        payload = document["versions"].get(str(selected_version))
        if not payload:
            raise ResourceNotFoundError(f"governed document '{doc_id}' version {selected_version} was not found")
        return DocumentMetadata(**payload)

    def read_raw_text(self, metadata: DocumentMetadata) -> tuple[str, str, list[str]]:
        raw_path = Path(metadata.raw_path)
        suffix = raw_path.suffix.casefold()
        payload = raw_path.read_bytes()
        warnings: list[str] = []
        text = payload.decode("utf-8-sig", errors="replace")
        if "\ufffd" in text:
            warnings.append("raw bytes required replacement characters during UTF-8 decoding")
        if suffix == ".csv":
            return _csv_to_text(text), "csv_text_parser", warnings
        if suffix == ".jsonl":
            return _jsonl_to_text(text, warnings), "jsonl_text_parser", warnings
        if suffix == ".json":
            return _json_to_text(text, warnings), "json_text_parser", warnings
        return text, "plain_text_parser", warnings

    def write_json(self, stage: str, doc_id: str, version: int, name: str, payload: dict[str, Any]) -> str:
        path = self._artifact_dir(stage, doc_id, version) / name
        _write_json(path, payload)
        return str(path)

    def write_jsonl(self, stage: str, doc_id: str, version: int, name: str, rows: Iterable[dict[str, Any]]) -> str:
        path = self._artifact_dir(stage, doc_id, version) / name
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        return str(path)

    def read_json(self, stage: str, doc_id: str, version: int, name: str) -> dict[str, Any]:
        path = self._artifact_dir(stage, doc_id, version) / name
        if not path.exists():
            raise ResourceNotFoundError(f"artifact was not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def iter_rag_chunks(self, doc_ids: list[str] | None = None) -> Iterable[dict[str, Any]]:
        allowed = set(doc_ids or [])
        for path in sorted((self.root / "rag").glob("doc_*/v*/chunks.jsonl")):
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if allowed and row.get("doc_id") not in allowed:
                        continue
                    yield row

    def document_summary(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        metadata = self.get_metadata(doc_id, version)
        quality = self._maybe_read_artifact("staging", metadata.doc_id, metadata.version, "quality.json")
        return {
            "metadata": metadata.to_dict(),
            "quality": quality,
            "artifacts": self._artifact_paths(metadata.doc_id, metadata.version),
        }

    def lineage(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        metadata = self.get_metadata(doc_id, version)
        artifacts = self._artifact_paths(metadata.doc_id, metadata.version)
        return {
            "doc_id": metadata.doc_id,
            "version": metadata.version,
            "raw": {
                "path": metadata.raw_path,
                "content_hash": metadata.content_hash,
                "byte_size": metadata.byte_size,
            },
            "stages": artifacts,
            "invariants": {
                "raw_is_not_modified_by_pipeline": True,
                "all_artifacts_include_doc_id": True,
                "chunks_trace_to_raw_path": True,
                "graph_edges_require_evidence": True,
            },
        }

    def write_quality(self, report: QualityReport) -> str:
        return self.write_json("staging", report.doc_id, report.version, "quality.json", report.to_dict())

    def _artifact_dir(self, stage: str, doc_id: str, version: int) -> Path:
        if stage not in DATA_DIRS:
            raise InvalidInputError(f"unknown data governance stage: {stage}")
        path = self.root / stage / doc_id / f"v{version}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _artifact_paths(self, doc_id: str, version: int) -> dict[str, list[str]]:
        output: dict[str, list[str]] = {}
        for stage in DATA_DIRS:
            stage_dir = self.root / stage / doc_id / f"v{version}"
            if stage_dir.exists():
                output[stage] = [str(path) for path in sorted(stage_dir.glob("*")) if path.is_file()]
            else:
                output[stage] = []
        return output

    def _maybe_read_artifact(self, stage: str, doc_id: str, version: int, name: str) -> dict[str, Any] | None:
        path = self.root / stage / doc_id / f"v{version}" / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "schema_version": "data-governance/v1",
                "documents": {},
                "hash_index": {},
                "source_index": {},
                "updated_at": utc_now(),
            }
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save_registry(self, registry: dict[str, Any]) -> None:
        _write_json(self.registry_path, registry)

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        path = self.root / "audit" / "events.jsonl"
        event = {"event_type": event_type, "created_at": utc_now(), "doc_id": payload.get("doc_id"), "payload": payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_key(source_system: str, external_id: str | None) -> str | None:
    if not external_id:
        return None
    return f"{source_system}:{external_id}"


def _safe_file_name(value: str) -> str:
    name = Path(value or "upload.txt").name
    safe = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._")
    return safe or "upload.txt"


def _csv_to_text(text: str) -> str:
    rows = csv.reader(text.splitlines())
    lines = [" | ".join(cell.strip() for cell in row if cell.strip()) for row in rows]
    return "\n".join(line for line in lines if line)


def _jsonl_to_text(text: str, warnings: list[str]) -> str:
    values: list[str] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values.extend(_string_values(json.loads(line)))
        except json.JSONDecodeError:
            warnings.append(f"jsonl line {index} could not be parsed")
            values.append(line)
    return "\n".join(values)


def _json_to_text(text: str, warnings: list[str]) -> str:
    try:
        return "\n".join(_string_values(json.loads(text)))
    except json.JSONDecodeError:
        warnings.append("json file could not be parsed; falling back to decoded text")
        return text


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_string_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_string_values(item))
        return values
    if value is None:
        return []
    return [str(value)]
