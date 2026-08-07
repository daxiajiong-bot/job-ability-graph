"""Settings for local LLM integrations."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class LLMSettings:
    backend: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_input_chars: int
    match_timeout_seconds: float = 45.0
    profile_timeout_seconds: float = 90.0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            backend=getenv("LLM_BACKEND", "mock").strip().lower(),
            base_url=getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip().rstrip("/"),
            api_key=getenv("LLM_API_KEY", "ollama"),
            model=getenv("LLM_MODEL", "qwen2.5:7b").strip(),
            timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 60.0, minimum=1.0, maximum=600.0),
            max_input_chars=_env_int("LLM_MAX_INPUT_CHARS", 12000, minimum=1000, maximum=200000),
            match_timeout_seconds=_env_float("LLM_MATCH_TIMEOUT_SECONDS", 45.0, minimum=5.0, maximum=600.0),
            profile_timeout_seconds=_env_float("LLM_PROFILE_TIMEOUT_SECONDS", 90.0, minimum=5.0, maximum=600.0),
        )


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw_value = getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value
