from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trend_discovery.batch import (
    SUBMIT_CONFIRMATION,
    download_batch,
    prepare_extraction_batch,
    refresh_batch_status,
    submit_batch,
    validate_model_payload,
)
from trend_discovery.dashscope import DashScopeBatchClient
from trend_discovery.io_utils import read_jsonl
from trend_discovery.schemas import Evidence, ExternalDocument


def _document() -> ExternalDocument:
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    return ExternalDocument(
        document_id="doc-1",
        source_type="job",
        source_name="company-careers",
        title="AI Agent 工程师",
        text="负责 Agent 开发，需要 Python。",
        raw_sha256="a" * 64,
        parser_version="test",
        company="示例公司",
        collected_at=now,
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="ev-1",
        document_id="doc-1",
        source_type="job",
        text="负责 Agent 开发，需要 Python。",
        text_sha256="b" * 64,
        char_start=0,
        char_end=24,
    )


class _FakeResponse:
    def __init__(self, *, value=None, content: bytes | None = None, status_code: int = 200):
        self._value = value
        self.content = content
        self.status_code = status_code
        self.text = "" if value is None else json.dumps(value)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._value


class _FakeHTTP:
    def __init__(self, result_content: bytes):
        self.calls: list[tuple[str, str, dict]] = []
        self.result_content = result_content

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "POST" and url.endswith("/files"):
            return _FakeResponse(value={"id": "file-input"})
        if method == "POST" and url.endswith("/batches"):
            return _FakeResponse(value={"id": "batch-1", "status": "validating"})
        if method == "GET" and url.endswith("/batches/batch-1"):
            return _FakeResponse(
                value={"id": "batch-1", "status": "completed", "output_file_id": "file-output"}
            )
        if method == "GET" and url.endswith("/files/file-output/content"):
            return _FakeResponse(content=self.result_content)
        raise AssertionError((method, url))


class _MustNotCall:
    def upload_file(self, *_args, **_kwargs):
        raise AssertionError("dry-run performed a network call")


def test_prepare_and_dry_run_need_no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    state = prepare_extraction_batch(
        [_document()], [_evidence()], tmp_path, run_id="run-1", model="qwen-flash"
    )
    assert state.phase == "prepared"
    assert state.request_count == 1
    request = next(read_jsonl(state.request_file))
    prompt = request["body"]["messages"][1]["content"]
    assert "evidence_id_whitelist" in prompt
    assert "ev-1" in prompt
    assert "DASHSCOPE_API_KEY" not in Path(state.request_file).read_text(encoding="utf-8")

    unchanged = submit_batch(tmp_path / "batch_state.json", client=_MustNotCall())
    assert unchanged.phase == "prepared"
    with pytest.raises(PermissionError, match=SUBMIT_CONFIRMATION):
        submit_batch(
            tmp_path / "batch_state.json",
            execute=True,
            confirmation="yes",
            client=_MustNotCall(),
        )


def test_fake_submit_status_download_and_validation(tmp_path: Path):
    state = prepare_extraction_batch(
        [_document()], [_evidence()], tmp_path, run_id="run-2", model="qwen-flash"
    )
    request = next(read_jsonl(state.request_file))
    custom_id = request["custom_id"]
    model_output = {
        "schema_version": "extraction_result_v1",
        "document_id": "doc-1",
        "facts": [
            {
                "fact_type": "required_skill",
                "value": "Python",
                "evidence_ids": ["ev-1"],
                "confidence": 0.95,
            }
        ],
        "summary": None,
    }
    result_row = {
        "custom_id": custom_id,
        "response": {
            "status_code": 200,
            "body": {
                "choices": [{"message": {"content": json.dumps(model_output)}}],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        },
        "error": None,
    }
    fake_http = _FakeHTTP((json.dumps(result_row) + "\n").encode())
    client = DashScopeBatchClient(http_client=fake_http)
    state_path = tmp_path / "batch_state.json"

    fake_key = "test-" + "only-key"
    submitted = submit_batch(
        state_path,
        execute=True,
        confirmation=SUBMIT_CONFIRMATION,
        client=client,
        api_key=fake_key,
    )
    assert submitted.phase == "running"
    assert submitted.input_file_id == "file-input"
    assert submitted.batch_id == "batch-1"

    completed = refresh_batch_status(state_path, client=client, api_key=fake_key)
    assert completed.phase == "completed"
    assert completed.output_file_id == "file-output"

    downloaded, counts = download_batch(state_path, client=client, api_key=fake_key)
    assert downloaded.phase == "downloaded"
    assert counts == {"accepted": 1, "rejected": 0, "expected": 1}
    accepted = next(read_jsonl(tmp_path / "validated_results.jsonl"))
    assert accepted["payload"]["facts"][0]["value"] == "Python"
    assert all(call[2]["headers"]["Authorization"] == f"Bearer {fake_key}" for call in fake_http.calls)


def test_bad_json_and_hallucinated_evidence_are_rejected():
    with pytest.raises(ValueError, match="not valid JSON"):
        validate_model_payload("not json", kind="extraction", allowed_evidence_ids=["ev-1"])
    with pytest.raises(ValueError, match="non-whitelisted"):
        validate_model_payload(
            {
                "schema_version": "extraction_result_v1",
                "document_id": "doc-1",
                "facts": [
                    {
                        "fact_type": "required_skill",
                        "value": "ImaginarySkill",
                        "evidence_ids": ["ev-hallucinated"],
                        "confidence": 1.0,
                    }
                ],
            },
            kind="extraction",
            allowed_evidence_ids=["ev-1"],
            expected_object_id="doc-1",
        )


def test_submit_detects_request_tampering(tmp_path: Path):
    state = prepare_extraction_batch(
        [_document()], [_evidence()], tmp_path, run_id="run-3", model="qwen-flash"
    )
    with Path(state.request_file).open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="changed after preparation"):
        submit_batch(
            tmp_path / "batch_state.json",
            execute=True,
            confirmation=SUBMIT_CONFIRMATION,
            client=_MustNotCall(),
        )
