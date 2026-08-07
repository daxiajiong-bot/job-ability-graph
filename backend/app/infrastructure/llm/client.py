"""OpenAI-compatible chat client used by local Ollama."""

from __future__ import annotations

from typing import Protocol

import httpx

from backend.app.infrastructure.llm.settings import LLMSettings


class LLMClientError(RuntimeError):
    """Raised when a local LLM call cannot produce a usable text response."""


class OpenAICompatibleChatClient:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        url = f"{self.settings.base_url}/chat/completions"
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMClientError(f"local LLM request failed: {exc}") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMClientError("local LLM response did not match the OpenAI-compatible schema") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("local LLM response content was empty")
        return content.strip()


class ChatClientProtocol(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str: ...
