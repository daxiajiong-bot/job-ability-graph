"""Stable JDProfile and ResumeProfile extraction schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.app.domain.entities import DocumentType


PROFILE_SCHEMA_VERSION = "profile-extraction/v2"
PROFILE_EVIDENCE_MAX_CHARS = 120


class ProfileSchemaError(ValueError):
    """Raised when extracted profile JSON violates the schema contract."""


@dataclass(frozen=True)
class ProfileSchema:
    name: str
    document_type: DocumentType
    object_keys: tuple[str, ...]
    list_keys: tuple[str, ...]
    evidence_required_list_keys: tuple[str, ...]

    @property
    def required_keys(self) -> set[str]:
        return {"schema_version", "document_type", *self.object_keys, *self.list_keys}


RESUME_PROFILE_SCHEMA = ProfileSchema(
    name="ResumeProfile",
    document_type=DocumentType.RESUME,
    object_keys=("candidate", "career_intent"),
    list_keys=(
        "education",
        "work_experience",
        "project_experience",
        "skills",
        "capabilities",
        "certificates",
        "languages",
        "achievements",
    ),
    evidence_required_list_keys=(
        "education",
        "work_experience",
        "project_experience",
        "skills",
        "capabilities",
        "certificates",
        "languages",
        "achievements",
    ),
)


JD_PROFILE_SCHEMA = ProfileSchema(
    name="JDProfile",
    document_type=DocumentType.JD,
    object_keys=("job", "company", "employment"),
    list_keys=(
        "responsibilities",
        "requirements",
        "skills",
        "capabilities",
        "application_scenarios",
        "evaluation_signals",
    ),
    evidence_required_list_keys=(
        "responsibilities",
        "requirements",
        "skills",
        "capabilities",
        "application_scenarios",
        "evaluation_signals",
    ),
)


def schema_for_document_type(document_type: DocumentType) -> ProfileSchema:
    if document_type is DocumentType.RESUME:
        return RESUME_PROFILE_SCHEMA
    if document_type is DocumentType.JD:
        return JD_PROFILE_SCHEMA
    raise ProfileSchemaError(f"profile extraction does not support document type '{document_type.value}'")


def normalize_profile_payload(
    payload: dict[str, Any],
    expected_document_type: DocumentType,
    *,
    source_text: str = "",
) -> dict[str, Any]:
    schema = schema_for_document_type(expected_document_type)
    _validate_required_keys(payload, schema)
    if payload.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileSchemaError(
            f"schema_version must be '{PROFILE_SCHEMA_VERSION}', got {payload.get('schema_version')!r}"
        )
    if payload.get("document_type") != expected_document_type.value:
        raise ProfileSchemaError(
            f"document_type must be '{expected_document_type.value}', got {payload.get('document_type')!r}"
        )

    normalized: dict[str, Any] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": expected_document_type.value,
    }
    warnings: list[str] = []
    evidence: list[dict[str, str]] = []
    evidence_ids_by_quote: dict[str, str] = {}
    legacy_evidence_by_id = _legacy_evidence_by_id(payload.get("evidence"), source_text, warnings)
    for key in schema.object_keys:
        normalized[key] = _object(payload.get(key))
    for key in schema.list_keys:
        normalized[key] = _normalize_list_items(
            _list(payload.get(key)),
            key,
            source_text,
            warnings,
            evidence,
            evidence_ids_by_quote,
            legacy_evidence_by_id,
        )

    if not evidence:
        detail = f": {'; '.join(warnings[:3])}" if warnings else ""
        raise ProfileSchemaError(f"no evidence-backed list items remained{detail}")
    normalized["evidence"] = evidence
    normalized["_warnings"] = warnings
    _add_legacy_aliases(normalized, expected_document_type)
    return normalized


def _validate_required_keys(payload: dict[str, Any], schema: ProfileSchema) -> None:
    missing = sorted(schema.required_keys - payload.keys())
    if missing:
        raise ProfileSchemaError(f"model output is missing required keys: {', '.join(missing)}")
    for key in schema.object_keys:
        if not isinstance(payload.get(key), dict):
            raise ProfileSchemaError(f"{key} must be an object")
    for key in schema.list_keys:
        if not isinstance(payload.get(key), list):
            raise ProfileSchemaError(f"{key} must be a list")


def _legacy_evidence_by_id(value: Any, source_text: str, warnings: list[str]) -> dict[str, str]:
    evidence_by_id: dict[str, str] = {}
    for index, item in enumerate(_list(value), start=1):
        try:
            normalized = _normalize_evidence(item, source_text)
        except ProfileSchemaError as exc:
            warnings.append(f"legacy evidence[{index}] ignored: {exc}")
            continue
        evidence_by_id[normalized["id"]] = normalized["text"]
    return evidence_by_id


def _normalize_evidence(item: Any, source_text: str) -> dict[str, str]:
    if not isinstance(item, dict):
        raise ProfileSchemaError("each evidence item must be an object")
    evidence_id = _clean_text(item.get("id"))
    text = _clean_text(item.get("text"))
    if not evidence_id or not text:
        raise ProfileSchemaError("each evidence item must include id and text")
    if len(text) > PROFILE_EVIDENCE_MAX_CHARS:
        raise ProfileSchemaError(f"evidence '{evidence_id}' exceeds {PROFILE_EVIDENCE_MAX_CHARS} characters")
    if source_text and not _contains_quote(source_text, text):
        raise ProfileSchemaError(f"evidence '{evidence_id}' text must be copied from the source document")
    return {
        "id": evidence_id,
        "field": _clean_text(item.get("field")) or "unknown",
        "text": text,
    }


def _normalize_list_items(
    items: list[Any],
    field: str,
    source_text: str,
    warnings: list[str],
    evidence: list[dict[str, str]],
    evidence_ids_by_quote: dict[str, str],
    legacy_evidence_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"{field}[{index}] ignored: item must be an object")
            continue
        item_payload = dict(item)
        if not _has_content(item_payload):
            continue
        evidence_text = _evidence_text_for_item(item_payload, legacy_evidence_by_id)
        if not evidence_text:
            warnings.append(f"{field}[{index}] ignored: missing evidence_text")
            continue
        if len(evidence_text) > PROFILE_EVIDENCE_MAX_CHARS:
            warnings.append(f"{field}[{index}] ignored: evidence_text exceeds {PROFILE_EVIDENCE_MAX_CHARS} characters")
            continue
        if source_text and not _contains_quote(source_text, evidence_text):
            warnings.append(f"{field}[{index}] ignored: evidence_text must be copied from the source document")
            continue
        evidence_id = _evidence_id_for_quote(field, evidence_text, evidence, evidence_ids_by_quote)
        item_payload.pop("evidence_text", None)
        item_payload["evidence_ids"] = [evidence_id]
        normalized_items.append(item_payload)
    return normalized_items


def _evidence_text_for_item(item: dict[str, Any], legacy_evidence_by_id: dict[str, str]) -> str:
    evidence_text = _clean_text(item.get("evidence_text"))
    if evidence_text:
        return evidence_text
    for evidence_id in _list_of_text(item.get("evidence_ids")):
        if evidence_id in legacy_evidence_by_id:
            return legacy_evidence_by_id[evidence_id]
    evidence_id = _clean_text(item.get("evidence_id"))
    return legacy_evidence_by_id.get(evidence_id, "")


def _evidence_id_for_quote(
    field: str,
    quote: str,
    evidence: list[dict[str, str]],
    evidence_ids_by_quote: dict[str, str],
) -> str:
    key = _normalize_for_match(quote)
    if key in evidence_ids_by_quote:
        return evidence_ids_by_quote[key]
    evidence_id = f"ev_{len(evidence) + 1:03d}"
    evidence_ids_by_quote[key] = evidence_id
    evidence.append({"id": evidence_id, "field": field, "text": quote})
    return evidence_id


def _has_content(item: dict[str, Any]) -> bool:
    ignored_keys = {"evidence_text", "evidence_ids", "evidence_id"}
    for key, value in item.items():
        if key in ignored_keys:
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if value is not None and not isinstance(value, (str, list, dict)):
            return True
    return False


def _add_legacy_aliases(payload: dict[str, Any], document_type: DocumentType) -> None:
    if document_type is DocumentType.RESUME:
        payload["experience"] = list(payload["work_experience"])
        payload["projects"] = list(payload["project_experience"])
        payload["responsibilities"] = []
        payload["requirements"] = []
        return
    payload["education"] = []
    payload["experience"] = []
    payload["projects"] = []
    payload["candidate"] = {"name": None, "target_position": None}


def _contains_quote(source_text: str, quote: str) -> bool:
    source_norm = _normalize_for_match(source_text)
    quote_norm = _normalize_for_match(quote)
    return bool(quote_norm and quote_norm in source_norm)


def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_of_text(value: Any) -> list[str]:
    return [_clean_text(item) for item in _list(value) if _clean_text(item)]


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
