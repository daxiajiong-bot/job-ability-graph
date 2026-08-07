from __future__ import annotations

from .schemas import JDProfile


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _section(title: str, body: str) -> str:
    return f"[{title}]\n{body}"


def _list_lines(items: list[str]) -> str:
    return "；\n".join(_dedupe_preserve(items))


def _skills_by_level(profile: JDProfile, level: str) -> list[str]:
    names = [skill.name for skill in profile.skills if skill.level == level]
    return _dedupe_preserve(names)


def serialize_profile(profile: JDProfile) -> str:
    sections: list[str] = []

    if profile.title:
        sections.append(_section("岗位名称", profile.title))
    if profile.responsibilities:
        sections.append(_section("岗位职责", _list_lines(profile.responsibilities)))
    if profile.requirements:
        sections.append(_section("任职要求", _list_lines(profile.requirements)))

    required = _skills_by_level(profile, "required")
    mentioned = _skills_by_level(profile, "mentioned")
    preferred = _skills_by_level(profile, "preferred")
    if required:
        sections.append(_section("必需技能", "；".join(required)))
    if mentioned:
        sections.append(_section("相关技能", "；".join(mentioned)))
    if preferred:
        sections.append(_section("优先技能", "；".join(preferred)))

    if profile.constraints.education.value:
        sections.append(_section("学历要求", profile.constraints.education.value))
    if profile.constraints.experience_years.value is not None:
        sections.append(_section("经验要求", f"{profile.constraints.experience_years.value}年以上"))
    if profile.constraints.location.value:
        sections.append(_section("工作地点", profile.constraints.location.value))

    return "\n\n".join(sections)

