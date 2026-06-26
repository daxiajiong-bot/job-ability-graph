"""Adapters that connect local LLM extraction to the v3 ports."""

from __future__ import annotations

from typing import Any

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.infrastructure.llm.client import ChatClientProtocol, OpenAICompatibleChatClient
from backend.app.infrastructure.llm.normalization import normalize_skills
from backend.app.infrastructure.llm.parser import ExtractionValidationError, parse_extraction_json
from backend.app.infrastructure.llm.prompts import extraction_messages
from backend.app.infrastructure.llm.settings import LLMSettings
from backend.app.infrastructure.mocks.adapters import NOT_IMPLEMENTED


class OllamaStructuredExtractor:
    def __init__(self, settings: LLMSettings, chat_client: ChatClientProtocol | None = None) -> None:
        self.settings = settings
        self.chat_client = chat_client or OpenAICompatibleChatClient(settings)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        if document.document_type not in {DocumentType.RESUME, DocumentType.JD}:
            return _extraction_fallback(f"LLM extraction does not support document type '{document.document_type.value}'.")
        messages = extraction_messages(document, self.settings.max_input_chars)
        try:
            content = self.chat_client.chat(messages)
            fields = parse_extraction_json(content, document.document_type)
        except (ExtractionValidationError, Exception) as exc:
            return _extraction_fallback(f"Ollama structured extraction failed: {exc}")
        return {
            "state": "available",
            "implementation": "ollama",
            "model": self.settings.model,
            "schema": "profile-extraction/v1",
            "fields": fields,
            "evidence": fields["evidence"],
            "warnings": [],
        }


class LightweightSkillNormalizer:
    def normalize(self, extraction: dict[str, Any]) -> dict[str, Any]:
        if extraction.get("state") != "available":
            return {
                "state": NOT_IMPLEMENTED,
                "implementation": "lightweight_skill_normalizer",
                "skills": [],
                "warnings": list(extraction.get("warnings", [])),
            }
        fields = dict(extraction.get("fields", {}))
        return {
            "state": "available",
            "implementation": "lightweight_skill_normalizer",
            "skills": normalize_skills(list(fields.get("skills", []))),
            "warnings": [],
        }


class LLMProfileBuilder:
    def build(
        self,
        profile_type: ProfileType,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]:
        if extraction.get("state") != "available":
            return _profile_fallback(profile_type, extraction)
        fields = dict(extraction.get("fields", {}))
        attributes = _base_attributes(profile_type)
        attributes.update(
            {
                "skills": list(normalization.get("skills", [])),
                "capabilities": list(fields.get("capabilities", [])),
                "education": list(fields.get("education", [])),
                "experience": list(fields.get("experience", [])),
                "projects": list(fields.get("projects", [])),
            }
        )
        if profile_type is ProfileType.CANDIDATE:
            candidate = dict(fields.get("candidate", {}))
            attributes["candidate"] = candidate
            attributes["target_position"] = candidate.get("target_position")
        else:
            job = dict(fields.get("job", {}))
            attributes["job"] = job
            attributes["job_title"] = job.get("title")
            attributes["requirements"] = list(fields.get("requirements", []))
            attributes["responsibilities"] = list(fields.get("responsibilities", []))

        return {
            "state": "available",
            "implementation": "llm_profile_builder",
            "attributes": attributes,
            "evidence": list(fields.get("evidence", [])),
            "warnings": [
                *list(extraction.get("warnings", [])),
                *list(normalization.get("warnings", [])),
            ],
        }


def _extraction_fallback(reason: str) -> dict[str, Any]:
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "reason": reason,
        "fields": {},
        "evidence": [],
        "warnings": [reason],
    }


def _profile_fallback(profile_type: ProfileType, extraction: dict[str, Any]) -> dict[str, Any]:
    reason = str(extraction.get("reason") or "LLM structured extraction is unavailable.")
    warnings = [reason, *list(extraction.get("warnings", []))]
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "attributes": _base_attributes(profile_type),
        "evidence": [],
        "warnings": _deduplicate(warnings),
    }


def _base_attributes(profile_type: ProfileType) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "skills": [],
        "capabilities": [],
        "education": [],
        "experience": [],
        "projects": [],
    }
    if profile_type is ProfileType.JOB:
        attributes.update({"job": {}, "job_title": None, "requirements": [], "responsibilities": []})
    else:
        attributes.update({"candidate": {}, "target_position": None})
    return attributes


def _deduplicate(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
