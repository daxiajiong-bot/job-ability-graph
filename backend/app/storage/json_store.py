"""JSON file storage helpers for demo artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from backend.app.storage import paths
from backend.app.storage.id_generator import make_doc_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_json(path: str | Path, data: Any) -> Path:
    file_path = Path(path)
    ensure_dir(file_path.parent)
    temp_path = file_path.with_name(f".{file_path.name}.{os.getpid()}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(file_path)
    return file_path


def load_json(path: str | Path, default: Any = None) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open(encoding="utf-8") as file:
        return json.load(file)


def append_json_list(path: str | Path, item: Any) -> Path:
    items = load_json(path, default=[])
    if not isinstance(items, list):
        items = []
    items.append(item)
    return save_json(path, items)


def _json_name(identifier: str) -> str:
    return f"{identifier}.json"


def _raw_dir(doc_type: str) -> Path:
    if doc_type == "jd":
        return paths.RAW_JD_DIR
    if doc_type == "resume":
        return paths.RAW_RESUME_DIR
    return paths.RAW_DIR / doc_type


def save_raw_document(doc_type: str, raw_text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = metadata or {}
    doc_id = str(metadata.get("doc_id") or make_doc_id(doc_type, raw_text or metadata.get("name", "")))
    target_path = _raw_dir(doc_type) / _json_name(doc_id)
    record = {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "created_at": utc_now(),
        "raw_text": raw_text,
        "metadata": metadata,
        "path": str(target_path),
    }
    save_json(target_path, record)
    return record


def save_parsed_profile(profile_type: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = str(profile.get("doc_id") or profile.get("profile_id") or make_doc_id(profile_type, json.dumps(profile, ensure_ascii=False, sort_keys=True)))
    if profile_type == "jd":
        target_dir = paths.PARSED_JD_PROFILES_DIR
    elif profile_type == "resume":
        target_dir = paths.PARSED_RESUME_PROFILES_DIR
    else:
        target_dir = paths.PARSED_DIR / profile_type
    target_path = target_dir / _json_name(doc_id)
    record = {
        "doc_id": doc_id,
        "profile_type": profile_type,
        "created_at": utc_now(),
        "profile": profile,
        "path": str(target_path),
    }
    save_json(target_path, record)
    return record


def save_match_result(match_result: Dict[str, Any]) -> Dict[str, Any]:
    match_id = str(match_result["match_id"])
    target_path = paths.MATCHES_DIR / _json_name(match_id)
    record = {
        "match_id": match_id,
        "created_at": utc_now(),
        **match_result,
        "path": str(target_path),
    }
    save_json(target_path, record)
    return record


def save_graph(graph_name: str, graph_data: Dict[str, Any]) -> Dict[str, Any]:
    graph_id = str(graph_data.get("graph_id") or graph_name)
    target_path = paths.GRAPH_DIR / _json_name(graph_id)
    record = {
        "graph_id": graph_id,
        "graph_name": graph_name,
        "created_at": utc_now(),
        "graph": graph_data,
        "path": str(target_path),
    }
    save_json(target_path, record)
    return record


def save_evidence_items(evidence_items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(evidence_items)
    target_path = paths.EVIDENCE_DIR / "evidence_index.json"
    record = {
        "created_at": utc_now(),
        "count": len(items),
        "items": items,
        "path": str(target_path),
    }
    save_json(target_path, record)
    return record
