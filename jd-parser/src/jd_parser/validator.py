from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from .schemas import JDProfile, ValidationResult


ALLOWED_TOP_LEVEL = {
    "schema_version",
    "document_id",
    "document_type",
    "title",
    "responsibilities",
    "requirements",
    "preferred",
    "skills",
    "constraints",
    "raw_text",
}


def _contains_evidence(evidence: str | None, source_texts: list[str]) -> bool:
    if not evidence:
        return False
    compact_evidence = re.sub(r"\s+", "", evidence)
    return any(evidence in text or compact_evidence in re.sub(r"\s+", "", text) for text in source_texts)


def _dedupe_skills(profile: JDProfile) -> tuple[JDProfile, list[str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    warnings = []
    for skill in profile.skills:
        key = (skill.name, skill.level, skill.evidence)
        if key in seen:
            warnings.append(f"duplicate skill removed: {skill.name}")
            continue
        seen.add(key)
        deduped.append(skill)
    if len(deduped) != len(profile.skills):
        profile = profile.model_copy(update={"skills": deduped})
    return profile, warnings


def validate_profile(profile_data: JDProfile | dict[str, Any], raw_text: str | None = None, cleaned_text: str | None = None) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if isinstance(profile_data, dict):
        extra = sorted(set(profile_data) - ALLOWED_TOP_LEVEL)
        for field in extra:
            errors.append(f"schema extra field: {field}")
        try:
            profile = JDProfile.model_validate(profile_data)
        except ValidationError as exc:
            return ValidationResult(
                document_id=str(profile_data.get("document_id") or ""),
                status="invalid",
                profile=None,
                validation_errors=errors + [str(exc)],
                validation_warnings=warnings,
            )
    else:
        profile = profile_data

    profile, dedupe_warnings = _dedupe_skills(profile)
    warnings.extend(dedupe_warnings)

    source_texts = [profile.raw_text]
    if raw_text:
        source_texts.append(raw_text)
    if cleaned_text:
        source_texts.append(cleaned_text)

    if not profile.document_id:
        errors.append("document_id is required")
    if profile.document_type != "job":
        errors.append("document_type must be job")
    if not profile.title:
        warnings.append("title is missing")
    if not isinstance(profile.responsibilities, list):
        errors.append("responsibilities must be an array")
    if not isinstance(profile.requirements, list):
        errors.append("requirements must be an array")
    if not isinstance(profile.preferred, list):
        errors.append("preferred must be an array")
    if not isinstance(profile.skills, list):
        errors.append("skills must be an array")

    for index, skill in enumerate(profile.skills):
        if skill.level not in {"required", "preferred", "mentioned"}:
            errors.append(f"skills[{index}].level is invalid: {skill.level}")
        if not skill.name:
            errors.append(f"skills[{index}].name is empty")
        if not skill.evidence:
            errors.append(f"skills[{index}].evidence is empty")
        elif not _contains_evidence(skill.evidence, source_texts):
            errors.append(f"skills[{index}].evidence not found in source: {skill.name}")

    education = profile.constraints.education
    if education.value and not education.evidence:
        errors.append("education evidence is empty while value is non-empty")
    if education.evidence and not _contains_evidence(education.evidence, source_texts):
        errors.append("education evidence not found in source")

    experience = profile.constraints.experience_years
    if experience.value is not None and experience.value < 0:
        errors.append("experience_years must be a non-negative integer or null")
    if experience.value is not None and not experience.evidence:
        errors.append("experience_years evidence is empty while value is non-empty")
    if experience.evidence and not _contains_evidence(experience.evidence, source_texts):
        errors.append("experience_years evidence not found in source")

    location = profile.constraints.location
    if location.value and not location.evidence:
        errors.append("location evidence is empty while value is non-empty")
    if location.evidence and not _contains_evidence(location.evidence, source_texts):
        errors.append("location evidence not found in source")

    status = "valid"
    if errors:
        status = "invalid"
    elif not profile.title:
        status = "needs_review"

    return ValidationResult(
        document_id=profile.document_id,
        status=status,
        profile=profile,
        validation_errors=errors,
        validation_warnings=warnings,
    )

