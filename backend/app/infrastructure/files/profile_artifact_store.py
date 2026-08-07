"""Filesystem persistence for parsed JDProfile and ResumeProfile artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.domain.entities import Profile, SourceDocument, utc_now
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION


class ProfileArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        profile: Profile,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]:
        path = self.root / profile.profile_type.value / f"{profile.id}.json"
        artifact_info = {
            "profile_json": str(path),
            "schema_version": PROFILE_SCHEMA_VERSION,
            "storage": "filesystem",
        }
        profile_payload = profile.public()
        profile_payload["artifacts"] = artifact_info
        payload = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "artifact_type": f"{profile.profile_type.value}_profile",
            "created_at": utc_now(),
            "source_document": document.public(),
            "profile": profile_payload,
            "extraction": _artifact_extraction(extraction),
            "normalization": _artifact_normalization(normalization),
        }
        _write_json(path, payload)
        return artifact_info


def _artifact_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": extraction.get("state"),
        "implementation": extraction.get("implementation"),
        "model": extraction.get("model"),
        "schema": extraction.get("schema"),
        "fields": extraction.get("fields", {}),
        "evidence": extraction.get("evidence", []),
        "raw_model_output": extraction.get("raw_model_output", ""),
        "validation_error": extraction.get("validation_error", ""),
        "reason": extraction.get("reason", ""),
        "warnings": extraction.get("warnings", []),
    }


def _artifact_normalization(normalization: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": normalization.get("state"),
        "implementation": normalization.get("implementation"),
        "skills": normalization.get("skills", []),
        "warnings": normalization.get("warnings", []),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
