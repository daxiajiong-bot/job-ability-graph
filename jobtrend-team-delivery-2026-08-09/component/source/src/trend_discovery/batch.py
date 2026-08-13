"""Preparation, lifecycle management, and validation for DashScope batches."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .dashscope import DashScopeBatchClient
from .io_utils import read_jsonl, sha256_file, stable_id, write_json, write_jsonl
from .schemas import Evidence, ExternalDocument


SUBMIT_CONFIRMATION = "SUBMIT_JOBTREND_PAID_BATCH"
BATCH_ENDPOINT = "/v1/chat/completions"
MAX_BATCH_REQUESTS = 50_000
MAX_BATCH_FILE_BYTES = 500 * 1024 * 1024
MAX_BATCH_LINE_BYTES = 2 * 1024 * 1024
MAX_CUSTOM_ID_CHARS = 64
EXTRACTION_PROMPT_VERSION = "jobtrend_extraction_v1"
ROLE_DEFINITION_PROMPT_VERSION = "jobtrend_role_definition_v1"

BatchKind = Literal["extraction", "role_definition"]
BatchPhase = Literal["prepared", "submitted", "running", "completed", "failed", "downloaded"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedFactDraft(_StrictModel):
    fact_type: Literal[
        "job_title",
        "responsibility",
        "required_skill",
        "preferred_skill",
        "mentioned_skill",
        "industry_signal",
        "policy_signal",
    ]
    value: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def non_empty_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class ExtractionEnvelope(_StrictModel):
    schema_version: Literal["extraction_result_v1"] = "extraction_result_v1"
    document_id: str
    facts: list[ExtractedFactDraft]
    summary: str | None = None


class RoleAbilityDraft(_StrictModel):
    name: str
    category: Literal["K", "S", "Tech", "T", "L", "Skill", "unknown"] = "unknown"
    evidence_ids: list[str]


class RoleDefinitionEnvelope(_StrictModel):
    schema_version: Literal["role_definition_result_v1"] = "role_definition_result_v1"
    candidate_id: str
    canonical_title: str
    aliases: list[str] = Field(default_factory=list)
    core_responsibilities: list[str]
    required_skills: list[RoleAbilityDraft]
    preferred_skills: list[RoleAbilityDraft]
    typical_industry_scenarios: list[str]
    explanation: str
    evidence_ids: list[str]


class BatchTaskIndex(_StrictModel):
    custom_id: str
    kind: BatchKind
    object_id: str
    allowed_evidence_ids: list[str]
    response_schema: Literal["extraction_result_v1", "role_definition_result_v1"]


class BatchState(_StrictModel):
    schema_version: Literal["jobtrend_batch_state_v1"] = "jobtrend_batch_state_v1"
    run_id: str
    kind: BatchKind
    phase: BatchPhase = "prepared"
    created_at: datetime
    updated_at: datetime
    model: str
    prompt_version: str
    request_file: str
    request_sha256: str
    request_count: int = Field(ge=1)
    request_index_file: str
    request_index_sha256: str
    input_file_id: str | None = None
    batch_id: str | None = None
    remote_status: str | None = None
    output_file_id: str | None = None
    error_file_id: str | None = None
    result_file: str | None = None
    result_sha256: str | None = None
    failure_reason: str | None = None


class ValidatedBatchResult(_StrictModel):
    custom_id: str
    kind: BatchKind
    object_id: str
    payload: dict[str, Any]
    evidence_ids: list[str]
    usage: dict[str, int | float] = Field(default_factory=dict)


def _as_document(value: ExternalDocument | Mapping[str, Any]) -> ExternalDocument:
    return value if isinstance(value, ExternalDocument) else ExternalDocument.model_validate(value)


def _as_evidence(value: Evidence | Mapping[str, Any]) -> Evidence:
    return value if isinstance(value, Evidence) else Evidence.model_validate(value)


def _evidence_whitelist(evidences: Sequence[Evidence]) -> list[str]:
    values = [item.evidence_id for item in evidences]
    if len(values) != len(set(values)):
        raise ValueError("evidence whitelist contains duplicate evidence_id values")
    return values


def _render_evidence(evidences: Sequence[Evidence]) -> str:
    return "\n\n".join(
        f"[{item.evidence_id}] {item.text}" for item in evidences
    )


def build_extraction_messages(
    document: ExternalDocument | Mapping[str, Any],
    evidences: Sequence[Evidence | Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Create the versioned extraction prompt with an explicit evidence allowlist."""

    doc = _as_document(document)
    evidence_models = [_as_evidence(item) for item in evidences]
    for item in evidence_models:
        if item.document_id != doc.document_id:
            raise ValueError(
                f"evidence {item.evidence_id} belongs to {item.document_id}, not {doc.document_id}"
            )
    allowed = _evidence_whitelist(evidence_models)
    system = (
        "你是可审计的岗位与产业信号抽取器。只输出符合给定 JSON Schema 的 JSON；"
        "不得输出 Markdown。所有事实必须逐项引用 evidence_ids。只能引用白名单中的 ID，"
        "不得凭常识补充技能、职责、岗位或政策结论。证据不足时返回空 facts。"
    )
    user = (
        f"prompt_version={EXTRACTION_PROMPT_VERSION}\n"
        f"document_id={doc.document_id}\n"
        f"source_type={doc.source_type}\n"
        f"title={doc.title}\n"
        f"evidence_id_whitelist={json.dumps(allowed, ensure_ascii=False)}\n\n"
        f"证据：\n{_render_evidence(evidence_models)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_role_definition_messages(
    candidate_id: str,
    candidate: Mapping[str, Any],
    evidences: Sequence[Evidence | Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Create a role-definition prompt after deterministic candidate gating."""

    if not candidate_id.strip():
        raise ValueError("candidate_id must not be empty")
    evidence_models = [_as_evidence(item) for item in evidences]
    allowed = _evidence_whitelist(evidence_models)
    system = (
        "你只负责为已经通过统计门槛的新岗位候选生成定义，不判断候选是否成立。"
        "只输出符合给定 JSON Schema 的 JSON，不得输出 Markdown。岗位名称、职责、技能和"
        "行业场景必须有证据；每项技能必须引用 evidence_ids，且只能使用白名单中的 ID。"
        "不得创造白名单外引用或无证据事实。"
    )
    safe_candidate = json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True, default=str)
    user = (
        f"prompt_version={ROLE_DEFINITION_PROMPT_VERSION}\n"
        f"candidate_id={candidate_id}\n"
        f"candidate_statistics={safe_candidate}\n"
        f"evidence_id_whitelist={json.dumps(allowed, ensure_ascii=False)}\n\n"
        f"证据：\n{_render_evidence(evidence_models)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _response_format(kind: BatchKind) -> dict[str, Any]:
    model: type[BaseModel]
    name: str
    if kind == "extraction":
        model = ExtractionEnvelope
        name = "jobtrend_extraction"
    else:
        model = RoleDefinitionEnvelope
        name = "jobtrend_role_definition"
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": model.model_json_schema()},
    }


def _custom_id(prefix: str, object_id: str) -> str:
    value = stable_id(prefix, object_id, length=32).replace(":", "-")
    if len(value) > MAX_CUSTOM_ID_CHARS:
        raise ValueError(f"generated custom_id exceeds {MAX_CUSTOM_ID_CHARS} characters")
    return value


def _request(
    *,
    custom_id: str,
    model: str,
    messages: list[dict[str, str]],
    kind: BatchKind,
    temperature: float,
    enable_thinking: bool,
) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "enable_thinking": enable_thinking,
            "response_format": _response_format(kind),
        },
    }


def validate_batch_jsonl(path: str | Path) -> tuple[int, str]:
    """Validate provider limits, request shape, uniqueness, and return count/hash."""

    source = Path(path)
    size = source.stat().st_size
    if size > MAX_BATCH_FILE_BYTES:
        raise ValueError(f"batch file is {size} bytes; maximum is {MAX_BATCH_FILE_BYTES}")
    count = 0
    seen: set[str] = set()
    with source.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            if len(raw_line) > MAX_BATCH_LINE_BYTES:
                raise ValueError(
                    f"{source}:{line_number}: line exceeds {MAX_BATCH_LINE_BYTES} bytes"
                )
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{source}:{line_number}: invalid UTF-8 JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{source}:{line_number}: expected object")
            custom_id = row.get("custom_id")
            if not isinstance(custom_id, str) or not custom_id or len(custom_id) > MAX_CUSTOM_ID_CHARS:
                raise ValueError(f"{source}:{line_number}: invalid custom_id")
            if custom_id in seen:
                raise ValueError(f"{source}:{line_number}: duplicate custom_id {custom_id!r}")
            if row.get("method") != "POST" or row.get("url") != BATCH_ENDPOINT:
                raise ValueError(f"{source}:{line_number}: unsupported method or URL")
            body = row.get("body")
            if not isinstance(body, dict) or not body.get("model") or not body.get("messages"):
                raise ValueError(f"{source}:{line_number}: incomplete request body")
            seen.add(custom_id)
            count += 1
            if count > MAX_BATCH_REQUESTS:
                raise ValueError(f"batch has more than {MAX_BATCH_REQUESTS} requests")
    if count == 0:
        raise ValueError("batch must contain at least one request")
    return count, sha256_file(source)


def _write_prepared_batch(
    *,
    output_dir: str | Path,
    run_id: str,
    kind: BatchKind,
    model: str,
    requests: Iterable[dict[str, Any]],
    index_rows: Iterable[BatchTaskIndex],
) -> BatchState:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    request_path = target / f"{kind}_requests.jsonl"
    index_path = target / f"{kind}_request_index.jsonl"
    write_jsonl(request_path, requests)
    write_jsonl(index_path, index_rows)
    count, digest = validate_batch_jsonl(request_path)
    index_values = list(read_jsonl(index_path))
    if len(index_values) != count:
        raise ValueError("request index count does not match request count")
    index_ids = [BatchTaskIndex.model_validate(row).custom_id for row in index_values]
    request_ids = [str(row["custom_id"]) for row in read_jsonl(request_path)]
    if index_ids != request_ids:
        raise ValueError("request index custom_ids do not match request order")
    now = datetime.now(timezone.utc)
    state = BatchState(
        run_id=run_id,
        kind=kind,
        created_at=now,
        updated_at=now,
        model=model,
        prompt_version=(
            EXTRACTION_PROMPT_VERSION if kind == "extraction" else ROLE_DEFINITION_PROMPT_VERSION
        ),
        request_file=str(request_path.resolve()),
        request_sha256=digest,
        request_count=count,
        request_index_file=str(index_path.resolve()),
        request_index_sha256=sha256_file(index_path),
    )
    write_json(target / "batch_state.json", state)
    return state


def prepare_extraction_batch(
    documents: Iterable[ExternalDocument | Mapping[str, Any]],
    evidences: Iterable[Evidence | Mapping[str, Any]],
    output_dir: str | Path,
    *,
    run_id: str,
    model: str,
    temperature: float = 0.1,
    enable_thinking: bool = False,
) -> BatchState:
    """Prepare, but never submit, an extraction batch."""

    evidence_by_document: dict[str, list[Evidence]] = {}
    for raw in evidences:
        item = _as_evidence(raw)
        evidence_by_document.setdefault(item.document_id, []).append(item)

    requests: list[dict[str, Any]] = []
    index: list[BatchTaskIndex] = []
    document_ids: set[str] = set()
    for raw in documents:
        document = _as_document(raw)
        if document.document_id in document_ids:
            raise ValueError(f"duplicate document_id {document.document_id!r}")
        document_ids.add(document.document_id)
        allowed_evidence = evidence_by_document.get(document.document_id, [])
        custom_id = _custom_id("extract", document.document_id)
        requests.append(
            _request(
                custom_id=custom_id,
                model=model,
                messages=build_extraction_messages(document, allowed_evidence),
                kind="extraction",
                temperature=temperature,
                enable_thinking=enable_thinking,
            )
        )
        index.append(
            BatchTaskIndex(
                custom_id=custom_id,
                kind="extraction",
                object_id=document.document_id,
                allowed_evidence_ids=[item.evidence_id for item in allowed_evidence],
                response_schema="extraction_result_v1",
            )
        )
    return _write_prepared_batch(
        output_dir=output_dir,
        run_id=run_id,
        kind="extraction",
        model=model,
        requests=requests,
        index_rows=index,
    )


def prepare_role_definition_batch(
    candidates: Iterable[Mapping[str, Any]],
    evidence_by_id: Mapping[str, Evidence | Mapping[str, Any]],
    output_dir: str | Path,
    *,
    run_id: str,
    model: str,
    temperature: float = 0.1,
    enable_thinking: bool = False,
) -> BatchState:
    """Prepare definitions only for caller-supplied, already-gated candidates."""

    evidence_models = {key: _as_evidence(value) for key, value in evidence_by_id.items()}
    requests: list[dict[str, Any]] = []
    index: list[BatchTaskIndex] = []
    seen: set[str] = set()
    for raw in candidates:
        candidate = dict(raw)
        candidate_id = str(
            candidate.get("candidate_id") or candidate.get("role_id") or candidate.get("cluster_id") or ""
        ).strip()
        if not candidate_id:
            raise ValueError("role candidate requires candidate_id, role_id, or cluster_id")
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate_id {candidate_id!r}")
        seen.add(candidate_id)
        evidence_ids = candidate.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
            raise ValueError(f"candidate {candidate_id!r} has invalid evidence_ids")
        missing = [item for item in evidence_ids if item not in evidence_models]
        if missing:
            raise ValueError(f"candidate {candidate_id!r} references missing evidence: {missing}")
        allowed_evidence = [evidence_models[item] for item in evidence_ids]
        custom_id = _custom_id("role", candidate_id)
        requests.append(
            _request(
                custom_id=custom_id,
                model=model,
                messages=build_role_definition_messages(candidate_id, candidate, allowed_evidence),
                kind="role_definition",
                temperature=temperature,
                enable_thinking=enable_thinking,
            )
        )
        index.append(
            BatchTaskIndex(
                custom_id=custom_id,
                kind="role_definition",
                object_id=candidate_id,
                allowed_evidence_ids=evidence_ids,
                response_schema="role_definition_result_v1",
            )
        )
    return _write_prepared_batch(
        output_dir=output_dir,
        run_id=run_id,
        kind="role_definition",
        model=model,
        requests=requests,
        index_rows=index,
    )


def load_batch_state(path: str | Path) -> BatchState:
    return BatchState.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _save_state(path: str | Path, state: BatchState) -> BatchState:
    state.updated_at = datetime.now(timezone.utc)
    write_json(path, state)
    return state


def submit_batch(
    state_path: str | Path,
    *,
    execute: bool = False,
    confirmation: str | None = None,
    client: DashScopeBatchClient | Any | None = None,
    api_key: str | None = None,
) -> BatchState:
    """Submit a prepared batch only after both an execution flag and exact phrase."""

    state = load_batch_state(state_path)
    if not execute:
        return state
    if confirmation != SUBMIT_CONFIRMATION:
        raise PermissionError(f"paid submission requires exact confirmation: {SUBMIT_CONFIRMATION}")
    if state.phase != "prepared":
        raise ValueError(f"cannot submit batch in phase {state.phase!r}")
    count, digest = validate_batch_jsonl(state.request_file)
    if count != state.request_count or digest != state.request_sha256:
        raise ValueError("prepared request file changed after preparation")
    if sha256_file(state.request_index_file) != state.request_index_sha256:
        raise ValueError("prepared request index changed after preparation")

    remote = client or DashScopeBatchClient()
    if state.input_file_id is None:
        upload = remote.upload_file(state.request_file, api_key=api_key)
        input_file_id = upload.get("id")
        if not isinstance(input_file_id, str) or not input_file_id:
            raise ValueError("DashScope upload response is missing file id")
        state.input_file_id = input_file_id
        _save_state(state_path, state)
    created = remote.create_batch(
        state.input_file_id,
        endpoint=BATCH_ENDPOINT,
        metadata={"run_id": state.run_id, "kind": state.kind},
        api_key=api_key,
    )
    batch_id = created.get("id")
    if not isinstance(batch_id, str) or not batch_id:
        raise ValueError("DashScope create response is missing batch id")
    state.batch_id = batch_id
    state.remote_status = str(created.get("status") or "validating")
    state.phase = _phase_from_remote(state.remote_status)
    if state.phase == "completed":
        _apply_remote_files(state, created)
    return _save_state(state_path, state)


def _phase_from_remote(status: str) -> BatchPhase:
    normalized = status.strip().lower()
    if normalized in {"validating", "in_progress", "finalizing", "cancelling"}:
        return "running"
    if normalized == "completed":
        return "completed"
    if normalized in {"failed", "expired", "cancelled"}:
        return "failed"
    if normalized in {"created", "submitted", "queued"}:
        return "submitted"
    raise ValueError(f"unsupported remote batch status {status!r}")


def _apply_remote_files(state: BatchState, response: Mapping[str, Any]) -> None:
    output_file_id = response.get("output_file_id")
    error_file_id = response.get("error_file_id")
    state.output_file_id = output_file_id if isinstance(output_file_id, str) else None
    state.error_file_id = error_file_id if isinstance(error_file_id, str) else None
    errors = response.get("errors")
    if errors:
        state.failure_reason = json.dumps(errors, ensure_ascii=False, default=str)[:4000]


def refresh_batch_status(
    state_path: str | Path,
    *,
    client: DashScopeBatchClient | Any | None = None,
    api_key: str | None = None,
) -> BatchState:
    state = load_batch_state(state_path)
    if state.phase in {"prepared", "downloaded"}:
        return state
    if not state.batch_id:
        raise ValueError("submitted state is missing batch_id")
    response = (client or DashScopeBatchClient()).retrieve_batch(state.batch_id, api_key=api_key)
    status = response.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError("DashScope status response is missing status")
    state.remote_status = status
    state.phase = _phase_from_remote(status)
    _apply_remote_files(state, response)
    return _save_state(state_path, state)


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else stripped


def _all_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                found.update(str(candidate) for candidate in item)
            else:
                found.update(_all_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_all_evidence_ids(item))
    return found


def validate_model_payload(
    payload: str | Mapping[str, Any],
    *,
    kind: BatchKind,
    allowed_evidence_ids: Iterable[str],
    expected_object_id: str | None = None,
) -> BaseModel:
    """Pydantic-validate model JSON and reject every non-whitelisted citation."""

    if isinstance(payload, str):
        try:
            value = json.loads(_strip_json_fence(payload))
        except json.JSONDecodeError as exc:
            raise ValueError(f"model output is not valid JSON: {exc}") from exc
    elif isinstance(payload, Mapping):
        value = dict(payload)
    else:
        raise ValueError("model output must be a JSON object or JSON string")
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    model: type[BaseModel] = ExtractionEnvelope if kind == "extraction" else RoleDefinitionEnvelope
    try:
        validated = model.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"model output failed {kind} schema validation: {exc}") from exc
    expected_field = "document_id" if kind == "extraction" else "candidate_id"
    if expected_object_id is not None and getattr(validated, expected_field) != expected_object_id:
        raise ValueError(
            f"model output {expected_field} does not match request object_id {expected_object_id!r}"
        )
    allowed = set(allowed_evidence_ids)
    cited = _all_evidence_ids(validated.model_dump(mode="json"))
    hallucinated = sorted(cited - allowed)
    if hallucinated:
        raise ValueError(f"model output contains non-whitelisted evidence IDs: {hallucinated}")
    return validated


def _message_content(row: Mapping[str, Any]) -> tuple[Any, dict[str, int | float]]:
    if row.get("error"):
        raise ValueError(f"provider returned an error: {row['error']}")
    response = row.get("response")
    if not isinstance(response, Mapping):
        # Simple output is useful for deterministic offline caches and test fakes.
        if "output" in row:
            return row["output"], {}
        raise ValueError("batch row is missing response")
    status_code = response.get("status_code", 200)
    if not isinstance(status_code, int) or not 200 <= status_code < 300:
        raise ValueError(f"provider response status_code is {status_code!r}")
    body = response.get("body")
    if not isinstance(body, Mapping):
        raise ValueError("batch response body is missing")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("batch response has no choices")
    first = choices[0]
    if not isinstance(first, Mapping) or not isinstance(first.get("message"), Mapping):
        raise ValueError("batch response choice has no message")
    content = first["message"].get("content")
    if isinstance(content, list):
        text_parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, Mapping) and block.get("type") in {None, "text"}
        ]
        content = "".join(text_parts)
    if not isinstance(content, (str, Mapping)):
        raise ValueError("batch response message content is missing")
    usage = body.get("usage", {})
    numeric_usage = (
        {
            str(key): value
            for key, value in usage.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if isinstance(usage, Mapping)
        else {}
    )
    return content, numeric_usage


def validate_batch_results(
    result_path: str | Path,
    request_index_path: str | Path,
    accepted_path: str | Path,
    rejected_path: str | Path,
) -> dict[str, int]:
    """Split provider output into schema-valid accepted rows and auditable rejects."""

    index: dict[str, BatchTaskIndex] = {}
    for raw in read_jsonl(request_index_path):
        item = BatchTaskIndex.model_validate(raw)
        if item.custom_id in index:
            raise ValueError(f"duplicate custom_id in request index: {item.custom_id!r}")
        index[item.custom_id] = item
    accepted: list[ValidatedBatchResult] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, row in enumerate(read_jsonl(result_path), start=1):
        custom_id = row.get("custom_id")
        if not isinstance(custom_id, str) or custom_id not in index:
            rejected.append(
                {"custom_id": custom_id, "line_number": line_number, "error": "unknown custom_id"}
            )
            continue
        if custom_id in seen:
            rejected.append(
                {"custom_id": custom_id, "line_number": line_number, "error": "duplicate result"}
            )
            continue
        seen.add(custom_id)
        task = index[custom_id]
        try:
            content, usage = _message_content(row)
            validated = validate_model_payload(
                content,
                kind=task.kind,
                allowed_evidence_ids=task.allowed_evidence_ids,
                expected_object_id=task.object_id,
            )
            payload = validated.model_dump(mode="json")
            accepted.append(
                ValidatedBatchResult(
                    custom_id=custom_id,
                    kind=task.kind,
                    object_id=task.object_id,
                    payload=payload,
                    evidence_ids=sorted(_all_evidence_ids(payload)),
                    usage=usage,
                )
            )
        except (TypeError, ValueError, ValidationError) as exc:
            rejected.append(
                {"custom_id": custom_id, "line_number": line_number, "error": str(exc)[:4000]}
            )
    missing = sorted(set(index) - seen)
    rejected.extend({"custom_id": item, "error": "missing result"} for item in missing)
    write_jsonl(accepted_path, accepted)
    write_jsonl(rejected_path, rejected)
    return {"accepted": len(accepted), "rejected": len(rejected), "expected": len(index)}


def download_batch(
    state_path: str | Path,
    destination: str | Path | None = None,
    *,
    client: DashScopeBatchClient | Any | None = None,
    api_key: str | None = None,
    validate: bool = True,
) -> tuple[BatchState, dict[str, int] | None]:
    state = load_batch_state(state_path)
    if state.phase != "completed":
        raise ValueError(f"cannot download batch in phase {state.phase!r}")
    if not state.output_file_id:
        raise ValueError("completed batch has no output_file_id")
    state_file = Path(state_path)
    result_path = Path(destination) if destination else state_file.parent / "batch_results.jsonl"
    (client or DashScopeBatchClient()).download_file(
        state.output_file_id, result_path, api_key=api_key
    )
    state.result_file = str(result_path.resolve())
    state.result_sha256 = sha256_file(result_path)
    validation_counts: dict[str, int] | None = None
    if validate:
        validation_counts = validate_batch_results(
            result_path,
            state.request_index_file,
            result_path.with_name("validated_results.jsonl"),
            result_path.with_name("rejected_results.jsonl"),
        )
    state.phase = "downloaded"
    return _save_state(state_path, state), validation_counts


# CLI-oriented aliases with short, unsurprising names.
status_batch = refresh_batch_status
prepare_batch = prepare_extraction_batch


__all__ = [
    "BATCH_ENDPOINT",
    "BatchState",
    "BatchTaskIndex",
    "EXTRACTION_PROMPT_VERSION",
    "ExtractionEnvelope",
    "MAX_BATCH_FILE_BYTES",
    "MAX_BATCH_REQUESTS",
    "ROLE_DEFINITION_PROMPT_VERSION",
    "RoleDefinitionEnvelope",
    "SUBMIT_CONFIRMATION",
    "build_extraction_messages",
    "build_role_definition_messages",
    "download_batch",
    "load_batch_state",
    "prepare_batch",
    "prepare_extraction_batch",
    "prepare_role_definition_batch",
    "refresh_batch_status",
    "status_batch",
    "submit_batch",
    "validate_batch_jsonl",
    "validate_batch_results",
    "validate_model_payload",
]
