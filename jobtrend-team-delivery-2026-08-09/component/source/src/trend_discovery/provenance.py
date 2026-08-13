from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .io_utils import read_jsonl, sha256_file, sha256_text, stable_id, write_json
from .schemas import ArtifactInfo, RunManifest


def count_records(path: str | Path) -> int | None:
    source = Path(path)
    if source.suffix == ".jsonl":
        return sum(1 for _ in read_jsonl(source))
    if source.suffix == ".csv":
        with source.open("r", encoding="utf-8-sig") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    return None


def artifact_info(path: str | Path, base: str | Path | None = None) -> ArtifactInfo:
    source = Path(path).resolve()
    display = source.name
    if base is not None:
        try:
            display = str(source.relative_to(Path(base).resolve()))
        except ValueError:
            display = source.name
    return ArtifactInfo(path=display, sha256=sha256_file(source), records=count_records(source))


def graph_fingerprint(paths: Iterable[str | Path]) -> str:
    parts = []
    for path in sorted((Path(value).resolve() for value in paths), key=str):
        if not path.is_file():
            raise FileNotFoundError(path)
        parts.append(f"{path.name}:{sha256_file(path)}")
    return sha256_text("\n".join(parts))


def dependency_versions() -> dict[str, str]:
    names = ["pydantic", "duckdb", "pyarrow", "numpy", "scipy", "sklearn", "qdrant_client"]
    result: dict[str, str] = {}
    for name in names:
        try:
            module = __import__(name)
            result[name] = str(getattr(module, "__version__", "unknown"))
        except Exception:
            result[name] = "not-installed"
    return result


def git_revision(root: str | Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def new_run_manifest(
    *,
    config_sha256: str,
    model_ids: dict[str, str],
    baseline_graph_fingerprint: str | None = None,
    notes: dict[str, Any] | None = None,
) -> RunManifest:
    created_at = datetime.now(UTC)
    run_id = stable_id("run", created_at.isoformat(), config_sha256, length=16)
    runtime_notes = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dependencies": dependency_versions(),
    }
    runtime_notes.update(notes or {})
    return RunManifest(
        run_id=run_id,
        created_at=created_at,
        status="prepared",
        config_sha256=config_sha256,
        baseline_graph_fingerprint=baseline_graph_fingerprint,
        model_ids=model_ids,
        prompt_versions={
            "extraction": "jobtrend_extract_v1",
            "role_definition": "jobtrend_role_definition_v1",
        },
        notes=runtime_notes,
    )


def write_run_manifest(path: str | Path, manifest: RunManifest) -> None:
    write_json(path, manifest)


def read_run_manifest(path: str | Path) -> RunManifest:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunManifest.model_validate(value)
