"""Minimal DashScope Batch API adapter.

The adapter deliberately has no dependency on the DashScope SDK.  DashScope's
batch endpoints implement the OpenAI-compatible Files and Batches APIs, so a
small HTTP adapter is easier to test and, importantly, keeps credentials out of
prepared request files and run state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Protocol

import httpx

from .io_utils import sha256_file


API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_COMPLETION_WINDOW = "24h"


class DashScopeError(RuntimeError):
    """Raised for an invalid or unsuccessful DashScope response."""


class MissingAPIKeyError(DashScopeError):
    """Raised only when a paid/network operation is actually executed."""


class HTTPClient(Protocol):
    """The small surface used from ``httpx.Client`` and test fakes."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


def resolve_api_key(explicit: str | None = None) -> str:
    """Resolve a credential at execution time.

    Importing this module, constructing a client, and preparing a batch never
    reads the environment.  Callers only reach this function from a network
    method.
    """

    value = explicit if explicit is not None else os.environ.get(API_KEY_ENV)
    if value is None or not value.strip():
        raise MissingAPIKeyError(
            f"{API_KEY_ENV} is required for DashScope execution; "
            "batch preparation and dry-run do not require it"
        )
    return value.strip()


def _response_json(response: Any) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except Exception as exc:  # httpx and injected fakes expose this method
        status = getattr(response, "status_code", "unknown")
        body = getattr(response, "text", "")
        if not body:
            try:
                body = json.dumps(response.json(), ensure_ascii=False)
            except Exception:
                body = ""
        raise DashScopeError(f"DashScope HTTP {status}: {body[:1000]}") from exc
    try:
        value = response.json()
    except Exception as exc:
        raise DashScopeError("DashScope returned a non-JSON response") from exc
    if not isinstance(value, dict):
        raise DashScopeError("DashScope returned a JSON value that is not an object")
    return value


class DashScopeBatchClient:
    """OpenAI-compatible Files/Batches client with an injectable HTTP layer."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        http_client: HTTPClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = timeout
        self._http_client = http_client
        self._owns_client = http_client is None

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self.base_url!r}, "
            f"api_key={'<configured>' if self._api_key else None}, "
            f"timeout={self.timeout!r})"
        )

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            close = getattr(self._http_client, "close", None)
            if callable(close):
                close()
            self._http_client = None

    def __enter__(self) -> "DashScopeBatchClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _client(self) -> HTTPClient:
        if self._http_client is None:
            self._http_client = httpx.Client()
        return self._http_client

    def _headers(self, api_key: str | None) -> dict[str, str]:
        key = resolve_api_key(api_key if api_key is not None else self._api_key)
        return {"Authorization": f"Bearer {key}"}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self._client().request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(api_key),
            timeout=self.timeout,
            **kwargs,
        )
        return _response_json(response)

    def upload_file(self, path: str | Path, *, api_key: str | None = None) -> dict[str, Any]:
        """Upload a validated JSONL file with purpose ``batch``."""

        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        with source.open("rb") as handle:
            return self._request_json(
                "POST",
                "/files",
                api_key=api_key,
                data={"purpose": "batch"},
                files={"file": (source.name, handle, "application/jsonl")},
            )

    def create_batch(
        self,
        input_file_id: str,
        *,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = DEFAULT_COMPLETION_WINDOW,
        metadata: Mapping[str, str] | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        if not input_file_id.strip():
            raise ValueError("input_file_id must not be empty")
        body: dict[str, Any] = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        if metadata:
            body["metadata"] = dict(metadata)
        return self._request_json("POST", "/batches", api_key=api_key, json=body)

    def retrieve_batch(self, batch_id: str, *, api_key: str | None = None) -> dict[str, Any]:
        if not batch_id.strip():
            raise ValueError("batch_id must not be empty")
        return self._request_json("GET", f"/batches/{batch_id}", api_key=api_key)

    def cancel_batch(self, batch_id: str, *, api_key: str | None = None) -> dict[str, Any]:
        if not batch_id.strip():
            raise ValueError("batch_id must not be empty")
        return self._request_json("POST", f"/batches/{batch_id}/cancel", api_key=api_key)

    def download_file(
        self,
        file_id: str,
        destination: str | Path,
        *,
        api_key: str | None = None,
        expected_sha256: str | None = None,
    ) -> Path:
        """Atomically download a result file and optionally verify its digest."""

        if not file_id.strip():
            raise ValueError("file_id must not be empty")
        response = self._client().request(
            "GET",
            f"{self.base_url}/files/{file_id}/content",
            headers=self._headers(api_key),
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            status = getattr(response, "status_code", "unknown")
            body = getattr(response, "text", "")
            raise DashScopeError(f"DashScope HTTP {status}: {body[:1000]}") from exc

        content = getattr(response, "content", None)
        if content is None:
            text = getattr(response, "text", None)
            if text is None:
                raise DashScopeError("DashScope file response has no content")
            content = str(text).encode("utf-8")
        if not isinstance(content, bytes):
            content = bytes(content)

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary = Path(temporary_name)
            actual = sha256_file(temporary)
            if expected_sha256 and actual != expected_sha256:
                raise DashScopeError(
                    f"download checksum mismatch: expected {expected_sha256}, got {actual}"
                )
            os.replace(temporary, target)
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()
        return target


__all__ = [
    "API_KEY_ENV",
    "DEFAULT_BASE_URL",
    "DashScopeBatchClient",
    "DashScopeError",
    "MissingAPIKeyError",
    "resolve_api_key",
]
