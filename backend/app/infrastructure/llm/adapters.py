"""Adapters that connect local LLM extraction to the v3 ports."""

from __future__ import annotations

from typing import Any

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION
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
        content = ""
        try:
            content = self.chat_client.chat(messages)
            fields = parse_extraction_json(content, document.document_type, source_text=document.text)
            warnings = list(fields.pop("_warnings", []))
        except ExtractionValidationError as exc:
            return _extraction_fallback(
                f"Ollama structured extraction failed: {exc}",
                raw_model_output=content,
                validation_error=str(exc),
            )
        except Exception as exc:
            return _extraction_fallback(
                f"Ollama structured extraction failed: {exc}",
                raw_model_output=content,
                validation_error=str(exc),
            )
        return {
            "state": "available",
            "implementation": "ollama",
            "model": self.settings.model,
            "schema": PROFILE_SCHEMA_VERSION,
            "fields": fields,
            "evidence": fields["evidence"],
            "warnings": warnings,
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
        normalized_skills = list(normalization.get("skills", []))
        attributes.update(
            {
                "profile_schema": PROFILE_SCHEMA_VERSION,
                "skills": normalized_skills,
                "capabilities": list(fields.get("capabilities", [])),
                "education": list(fields.get("education", [])),
                "experience": list(fields.get("experience", fields.get("work_experience", []))),
                "projects": list(fields.get("projects", fields.get("project_experience", []))),
            }
        )
        if profile_type is ProfileType.CANDIDATE:
            candidate = dict(fields.get("candidate", {}))
            career_intent = dict(fields.get("career_intent", {}))
            attributes["candidate"] = candidate
            attributes["career_intent"] = career_intent
            attributes["target_position"] = career_intent.get("target_position") or candidate.get("target_position")
            attributes["resume_profile"] = _resume_profile(fields, normalized_skills)
        else:
            job = dict(fields.get("job", {}))
            attributes["job"] = job
            attributes["job_title"] = job.get("title")
            attributes["requirements"] = list(fields.get("requirements", []))
            attributes["responsibilities"] = list(fields.get("responsibilities", []))
            attributes["company"] = dict(fields.get("company", {}))
            attributes["employment"] = dict(fields.get("employment", {}))
            attributes["jd_profile"] = _jd_profile(fields, normalized_skills)

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


def _extraction_fallback(
    reason: str,
    *,
    raw_model_output: str = "",
    validation_error: str = "",
) -> dict[str, Any]:
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "reason": reason,
        "fields": {},
        "evidence": [],
        "raw_model_output": raw_model_output[:4000],
        "validation_error": validation_error,
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
        "profile_schema": PROFILE_SCHEMA_VERSION,
        "skills": [],
        "capabilities": [],
        "education": [],
        "experience": [],
        "projects": [],
    }
    if profile_type is ProfileType.JOB:
        attributes.update(
            {
                "job": {},
                "job_title": None,
                "company": {},
                "employment": {},
                "requirements": [],
                "responsibilities": [],
                "jd_profile": {},
            }
        )
    else:
        attributes.update({"candidate": {}, "career_intent": {}, "target_position": None, "resume_profile": {}})
    return attributes


def _resume_profile(fields: dict[str, Any], skills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.RESUME.value,
        "candidate": dict(fields.get("candidate", {})),
        "career_intent": dict(fields.get("career_intent", {})),
        "education": list(fields.get("education", [])),
        "work_experience": list(fields.get("work_experience", fields.get("experience", []))),
        "project_experience": list(fields.get("project_experience", fields.get("projects", []))),
        "skills": skills,
        "capabilities": list(fields.get("capabilities", [])),
        "certificates": list(fields.get("certificates", [])),
        "languages": list(fields.get("languages", [])),
        "achievements": list(fields.get("achievements", [])),
    }


def _jd_profile(fields: dict[str, Any], skills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": DocumentType.JD.value,
        "job": dict(fields.get("job", {})),
        "company": dict(fields.get("company", {})),
        "employment": dict(fields.get("employment", {})),
        "responsibilities": list(fields.get("responsibilities", [])),
        "requirements": list(fields.get("requirements", [])),
        "skills": skills,
        "capabilities": list(fields.get("capabilities", [])),
        "application_scenarios": list(fields.get("application_scenarios", [])),
        "evaluation_signals": list(fields.get("evaluation_signals", [])),
    }


def _deduplicate(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
