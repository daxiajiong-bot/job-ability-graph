"""Strict JSON parsing and schema validation for LLM extraction output."""

from __future__ import annotations

import json
from typing import Any

from backend.app.domain.entities import DocumentType


class ExtractionValidationError(ValueError):
    """Raised when model output is not valid extraction JSON."""


COMMON_REQUIRED_KEYS = {
    "document_type",
    "candidate",
    "education",
    "experience",
    "projects",
    "skills",
    "capabilities",
    "responsibilities",
    "requirements",
    "evidence",
}


def parse_extraction_json(content: str, expected_document_type: DocumentType) -> dict[str, Any]:
    raw = content.strip()
    if not raw.startswith("{") or not raw.endswith("}"):
        raise ExtractionValidationError("model output must be a JSON object without Markdown fences")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(f"model output was not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ExtractionValidationError("model output must be a JSON object")
    _validate_payload(payload, expected_document_type)
    return _normalize_payload(payload, expected_document_type)


def _validate_payload(payload: dict[str, Any], expected_document_type: DocumentType) -> None:
    missing = sorted(COMMON_REQUIRED_KEYS - payload.keys())
    if expected_document_type is DocumentType.JD and "job" not in payload:
        missing.append("job")
    if missing:
        raise ExtractionValidationError(f"model output is missing required keys: {', '.join(missing)}")
    if payload.get("document_type") != expected_document_type.value:
        raise ExtractionValidationError(
            f"model document_type must be '{expected_document_type.value}', got {payload.get('document_type')!r}"
        )
    if not isinstance(payload.get("candidate"), dict):
        raise ExtractionValidationError("candidate must be an object")
    if expected_document_type is DocumentType.JD and not isinstance(payload.get("job"), dict):
        raise ExtractionValidationError("job must be an object for JD extraction")
    for key in ["education", "experience", "projects", "skills", "capabilities", "responsibilities", "requirements"]:
        if not isinstance(payload.get(key), list):
            raise ExtractionValidationError(f"{key} must be a list")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ExtractionValidationError("evidence must be a list")
    for item in evidence:
        if not isinstance(item, dict):
            raise ExtractionValidationError("each evidence item must be an object")
        if not _clean_text(item.get("id")) or not _clean_text(item.get("text")):
            raise ExtractionValidationError("each evidence item must include id and text")


def _normalize_payload(payload: dict[str, Any], expected_document_type: DocumentType) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["document_type"] = expected_document_type.value
    normalized["candidate"] = _object(payload.get("candidate"))
    normalized["job"] = _object(payload.get("job"))
    for key in ["education", "experience", "projects", "skills", "capabilities", "responsibilities", "requirements"]:
        normalized[key] = [_object(item) for item in payload.get(key, []) if isinstance(item, dict)]
    normalized["evidence"] = [_normalize_evidence(item) for item in payload.get("evidence", []) if isinstance(item, dict)]
    return normalized


def _normalize_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean_text(item.get("id")),
        "field": _clean_text(item.get("field")) or "unknown",
        "text": _clean_text(item.get("text"))[:120],
    }


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
