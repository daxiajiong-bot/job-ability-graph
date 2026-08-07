from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from jd_resume_pipeline.batch_inputs import validate_batch_requests
from jd_resume_pipeline.batch_results import normalize_usage, response_body
from jd_resume_pipeline.io_utils import read_jsonl, write_json


BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CONFIRMATION_TEXT = "SUBMIT_QWEN_PAID_BATCH"


def require_api_key(environment: dict[str, str] | os._Environ[str] | None = None) -> str:
    environment = environment if environment is not None else os.environ
    api_key = environment.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")
    return api_key


def validate_execute_confirmation(execute: bool, confirmation: str | None) -> None:
    if not execute:
        return
    if confirmation != CONFIRMATION_TEXT:
        raise RuntimeError(
            f"paid submission requires --confirm {CONFIRMATION_TEXT}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: state must be a JSON object")
    return value


def save_state(path: Path, value: dict[str, Any]) -> None:
    write_json(path, value)


def _record_network_call(
    state_path: Path, state: dict[str, Any], operation: str
) -> None:
    count = state.get("network_calls")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        state["network_calls"] = count + 1
    else:
        state["network_calls"] = "unknown"
        state["network_calls_observed_after_reconciliation"] = (
            int(state.get("network_calls_observed_after_reconciliation", 0)) + 1
        )
    state["last_network_operation"] = operation
    save_state(state_path, state)


def validate_input_file(path: Path) -> tuple[list[dict[str, Any]], str]:
    requests = list(read_jsonl(path))
    if not requests:
        raise ValueError("Batch input is empty")
    errors = validate_batch_requests(requests)
    if errors:
        raise ValueError("invalid Batch input: " + "; ".join(errors))
    if len(requests) > 50_000:
        raise ValueError("Batch input exceeds 50,000 requests")
    if path.stat().st_size > 500 * 1024 * 1024:
        raise ValueError("Batch input exceeds 500 MB")
    if any(
        len(json.dumps(request, ensure_ascii=False).encode("utf-8")) > 6 * 1024 * 1024
        for request in requests
    ):
        raise ValueError("a Batch request line exceeds 6 MB")
    return requests, sha256_file(path)


class DashscopeBatchClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: int = 120) -> None:
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        expect_json: bool = True,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DashScope HTTP {exc.code}: {detail[:1000]}") from exc
        if not expect_json:
            return content
        try:
            value = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("DashScope returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("DashScope returned a non-object JSON response")
        return value

    def upload_file(self, path: Path) -> dict[str, Any]:
        boundary = f"----codex-batch-{uuid.uuid4().hex}"
        filename = path.name.replace('"', "")
        chunks = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="purpose"\r\n\r\n',
            b"batch\r\n",
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            ).encode(),
            b"Content-Type: application/jsonl\r\n\r\n",
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        return self._request(
            "POST",
            "/files",
            body=b"".join(chunks),
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def create_batch(
        self,
        input_file_id: str,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        if metadata:
            payload["metadata"] = metadata
        return self._request(
            "POST",
            "/batches",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )

    def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        return self._request("GET", f"/batches/{batch_id}")

    def download_file(self, file_id: str) -> bytes:
        return self._request(
            "GET", f"/files/{file_id}/content", expect_json=False
        )


def make_client() -> DashscopeBatchClient:
    return DashscopeBatchClient(require_api_key())


def submit(
    input_path: Path,
    state_path: Path,
    *,
    execute: bool = False,
    confirmation: str | None = None,
    client_factory: Callable[[], DashscopeBatchClient] = make_client,
) -> dict[str, Any]:
    requests, input_hash = validate_input_file(input_path)
    plan = {
        "dry_run": not execute,
        "action": "upload_and_create_batch",
        "input_path": str(input_path.resolve()),
        "request_count": len(requests),
        "input_sha256": input_hash,
        "state_path": str(state_path.resolve()),
        "endpoint": "/v1/chat/completions",
    }
    if not execute:
        return plan

    validate_execute_confirmation(execute, confirmation)
    state = load_state(state_path)
    if state.get("input_sha256") not in (None, input_hash):
        raise RuntimeError("state belongs to different input content")
    if "network_calls" not in state and not (
        state.get("input_file_id") or state.get("batch_id")
    ):
        state["network_calls"] = 0
    if state.get("batch_id"):
        state["submitted"] = True
    else:
        state.setdefault("submitted", False)
    state.update(
        {
            "input_path": str(input_path.resolve()),
            "input_sha256": input_hash,
            "request_count": len(requests),
            "endpoint": "/v1/chat/completions",
        }
    )
    client = client_factory()
    if not state.get("input_file_id"):
        _record_network_call(state_path, state, "upload_file")
        uploaded = client.upload_file(input_path)
        input_file_id = uploaded.get("id")
        if not isinstance(input_file_id, str) or not input_file_id:
            raise RuntimeError("upload response missing file id")
        state["input_file_id"] = input_file_id
        state["upload_response"] = uploaded
        save_state(state_path, state)
    if not state.get("batch_id"):
        _record_network_call(state_path, state, "create_batch")
        batch = client.create_batch(
            state["input_file_id"],
            metadata={
                "ds_name": input_path.stem,
                "input_sha256": input_hash,
            },
        )
        batch_id = batch.get("id")
        if not isinstance(batch_id, str) or not batch_id:
            raise RuntimeError("create response missing batch id")
        state["batch_id"] = batch_id
        state["submitted"] = True
        _update_state_from_batch(state, batch)
        save_state(state_path, state)
    save_state(state_path, state)
    return state


def _update_state_from_batch(state: dict[str, Any], batch: dict[str, Any]) -> None:
    for key in (
        "id",
        "status",
        "input_file_id",
        "output_file_id",
        "error_file_id",
        "request_counts",
        "created_at",
        "in_progress_at",
        "completed_at",
        "failed_at",
        "expires_at",
        "errors",
    ):
        if key in batch:
            target = "batch_id" if key == "id" else key
            state[target] = batch[key]
    if state.get("batch_id"):
        state["submitted"] = True
    state["last_batch_response"] = batch


def retrieve_status(
    state_path: Path,
    *,
    execute: bool = False,
    client_factory: Callable[[], DashscopeBatchClient] = make_client,
) -> dict[str, Any]:
    state = load_state(state_path)
    batch_id = state.get("batch_id")
    if not batch_id:
        raise RuntimeError("state does not contain batch_id")
    if not execute:
        return {
            "dry_run": True,
            "action": "retrieve_batch_status",
            "batch_id": batch_id,
            "state_path": str(state_path.resolve()),
        }
    client = client_factory()
    _record_network_call(state_path, state, "retrieve_batch")
    batch = client.retrieve_batch(batch_id)
    _update_state_from_batch(state, batch)
    save_state(state_path, state)
    return state


def token_usage_from_jsonl(path: Path) -> dict[str, int]:
    total: Counter[str] = Counter()
    successful_rows = 0
    for row in read_jsonl(path):
        try:
            body = response_body(row)
        except ValueError:
            continue
        usage = normalize_usage(body.get("usage"))
        total.update(usage)
        successful_rows += 1
    return {"successful_rows": successful_rows, **dict(total)}


def download_results(
    state_path: Path,
    output_path: Path,
    error_path: Path,
    *,
    execute: bool = False,
    client_factory: Callable[[], DashscopeBatchClient] = make_client,
) -> dict[str, Any]:
    state = load_state(state_path)
    if not state.get("batch_id"):
        raise RuntimeError("state does not contain batch_id")
    state["submitted"] = True
    if not execute:
        return {
            "dry_run": True,
            "action": "download_batch_files",
            "batch_id": state["batch_id"],
            "output_file_id": state.get("output_file_id"),
            "error_file_id": state.get("error_file_id"),
            "output_path": str(output_path.resolve()),
            "error_path": str(error_path.resolve()),
        }
    client = client_factory()
    if not state.get("output_file_id") and not state.get("error_file_id"):
        _record_network_call(state_path, state, "retrieve_batch")
        batch = client.retrieve_batch(state["batch_id"])
        _update_state_from_batch(state, batch)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.parent.mkdir(parents=True, exist_ok=True)
    if state.get("output_file_id"):
        _record_network_call(state_path, state, "download_output_file")
        output_path.write_bytes(client.download_file(state["output_file_id"]))
        state["output_path"] = str(output_path.resolve())
        actual_usage = token_usage_from_jsonl(output_path)
        # Batch cost is determined by every API-success response, regardless
        # of whether downstream semantic/quality validation accepts it.
        state["actual_token_usage"] = actual_usage
        state["token_usage_scope"] = "all_api_successful_responses"
    if state.get("error_file_id"):
        _record_network_call(state_path, state, "download_error_file")
        error_path.write_bytes(client.download_file(state["error_file_id"]))
        state["error_path"] = str(error_path.resolve())
    save_state(state_path, state)
    return state
