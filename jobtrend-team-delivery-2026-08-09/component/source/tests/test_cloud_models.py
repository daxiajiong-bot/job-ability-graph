import httpx
import pytest

from trend_discovery.cloud_models import (
    CloudModelError,
    DashScopeEmbeddingClient,
    DashScopeRerankClient,
)


class FakeResponse:
    def __init__(self, value: dict) -> None:
        self.value = value

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.value


class FakeClient:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.requests: list[dict] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value)  # type: ignore[arg-type]


def test_embedding_client_validates_dimension() -> None:
    fake = FakeClient([{"data": [{"embedding": [0.1, 0.2]}]}])
    client = DashScopeEmbeddingClient(
        dimension=2, api_key_value="test-key", client=fake, retries=1
    )
    assert client("Agent") == [0.1, 0.2]
    assert fake.requests[0]["json"]["dimensions"] == 2


def test_reranker_restores_input_order() -> None:
    fake = FakeClient(
        [{"output": {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]}}]
    )
    client = DashScopeRerankClient(api_key_value="test-key", client=fake, retries=1)
    assert client("query", ["one", "two"]) == [0.2, 0.9]


def test_cloud_call_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(CloudModelError, match="DASHSCOPE_API_KEY"):
        DashScopeEmbeddingClient()


def test_embedding_retries_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trend_discovery.cloud_models.time.sleep", lambda _: None)
    fake = FakeClient(
        [httpx.ReadTimeout("slow"), {"data": [{"embedding": [1.0]}]}]
    )
    client = DashScopeEmbeddingClient(
        dimension=1, api_key_value="test-key", client=fake, retries=2
    )
    assert client("query") == [1.0]
    assert len(fake.requests) == 2
