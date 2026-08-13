from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import httpx


class HTTPResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class HTTPClient(Protocol):
    def post(self, url: str, **kwargs: Any) -> HTTPResponse: ...


class CloudModelError(RuntimeError):
    pass


def api_key(explicit: str | None = None) -> str:
    value = explicit or os.environ.get("DASHSCOPE_API_KEY")
    if not value:
        raise CloudModelError("DASHSCOPE_API_KEY is required for a new cloud-model call")
    return value


class DashScopeEmbeddingClient:
    """Callable text-embedding-v4 adapter for ``HybridEvidenceIndex``."""

    def __init__(
        self,
        *,
        model: str = "text-embedding-v4",
        dimension: int = 1024,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_value: str | None = None,
        client: HTTPClient | None = None,
        timeout: float = 60.0,
        retries: int = 3,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key(api_key_value)
        self.client = client or httpx.Client(timeout=timeout)
        self.retries = max(1, retries)

    def __call__(self, text: str) -> list[float]:
        payload = {
            "model": self.model,
            "input": text,
            "dimensions": self.dimension,
            "encoding_format": "float",
        }
        value = _post_json(
            self.client,
            f"{self.base_url}/embeddings",
            payload,
            self.api_key,
            retries=self.retries,
        )
        try:
            vector = value["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise CloudModelError("embedding response is missing data[0].embedding") from exc
        if not isinstance(vector, list) or len(vector) != self.dimension:
            raise CloudModelError(
                f"embedding response dimension is {len(vector) if isinstance(vector, list) else 'invalid'}, "
                f"expected {self.dimension}"
            )
        return [float(item) for item in vector]


class DashScopeRerankClient:
    """Callable qwen3-rerank adapter preserving the caller's document order."""

    def __init__(
        self,
        *,
        model: str = "qwen3-rerank",
        endpoint: str = (
            "https://dashscope.aliyuncs.com/api/v1/services/"
            "rerank/text-rerank/text-rerank"
        ),
        api_key_value: str | None = None,
        client: HTTPClient | None = None,
        timeout: float = 60.0,
        retries: int = 3,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.api_key = api_key(api_key_value)
        self.client = client or httpx.Client(timeout=timeout)
        self.retries = max(1, retries)

    def __call__(self, query: str, documents: Sequence[Any]) -> list[float]:
        texts = [str(getattr(document, "text", document)) for document in documents]
        if not texts:
            return []
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": texts},
            "parameters": {"return_documents": False, "top_n": len(texts)},
        }
        value = _post_json(
            self.client,
            self.endpoint,
            payload,
            self.api_key,
            retries=self.retries,
        )
        scores = [0.0] * len(texts)
        try:
            results = value["output"]["results"]
            for result in results:
                scores[int(result["index"])] = float(result["relevance_score"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CloudModelError("rerank response has an invalid output.results payload") from exc
        return scores


def _post_json(
    client: HTTPClient,
    url: str,
    payload: Mapping[str, Any],
    key: str,
    *,
    retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=dict(payload),
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise CloudModelError("cloud-model response must be a JSON object")
            return value
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(2**attempt, 4))
    raise CloudModelError(f"cloud-model request failed after {retries} attempts: {last_error}")
