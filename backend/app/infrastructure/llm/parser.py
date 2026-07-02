"""Strict JSON parsing and JDProfile/ResumeProfile schema validation."""

from __future__ import annotations

import json
from typing import Any

from backend.app.domain.entities import DocumentType
from backend.app.domain.profile_schemas import ProfileSchemaError, normalize_profile_payload


class ExtractionValidationError(ValueError):
    """Raised when model output is not valid extraction JSON."""


def parse_extraction_json(
    content: str,
    expected_document_type: DocumentType,
    *,
    source_text: str = "",
) -> dict[str, Any]:
    raw = content.strip()
    if not raw.startswith("{") or not raw.endswith("}"):
        raise ExtractionValidationError("model output must be a JSON object without Markdown fences")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(f"model output was not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ExtractionValidationError("model output must be a JSON object")
    try:
        return normalize_profile_payload(payload, expected_document_type, source_text=source_text)
    except ProfileSchemaError as exc:
        raise ExtractionValidationError(str(exc)) from exc
