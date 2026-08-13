from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 20) -> str:
    encoded = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{sha256_text(encoded)[:length]}"


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{source}:{line_number}: expected a JSON object")
            yield value


def read_csv(path: str | Path) -> Iterator[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{source}: CSV header is missing")
        for row in reader:
            yield {str(key): str(value or "") for key, value in row.items()}


def _atomic_write(path: Path, writer: callable) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    _atomic_write(target, lambda handle: json.dump(payload, handle, ensure_ascii=False, indent=2))


def write_jsonl(path: str | Path, rows: Iterable[Any]) -> int:
    target = Path(path)
    count = 0

    def writer(handle: Any) -> None:
        nonlocal count
        for row in rows:
            payload = row.model_dump(mode="json") if isinstance(row, BaseModel) else row
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1

    _atomic_write(target, writer)
    return count


def model_json_schema(model: type[T]) -> dict[str, Any]:
    return model.model_json_schema()
