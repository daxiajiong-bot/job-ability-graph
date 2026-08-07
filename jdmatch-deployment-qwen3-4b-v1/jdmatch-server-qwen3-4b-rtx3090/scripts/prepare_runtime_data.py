#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/embedding/serialized_v1"
DEFAULT_OUTPUT = ROOT / "data/runtime"
RUNTIME_FILES = ("jds.jsonl", "resumes.jsonl", "sampling_contracts.jsonl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonl_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for line in handle if line.strip())


def prepare_runtime_data(source: Path, output: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    missing = [str(source / name) for name in RUNTIME_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing serialized runtime inputs: {missing}")

    output.mkdir(parents=True, exist_ok=True)
    manifest_files: dict[str, Any] = {}
    for name in RUNTIME_FILES:
        source_path = source / name
        output_path = output / name
        shutil.copy2(source_path, output_path)
        manifest_files[name] = {
            "rows": jsonl_count(output_path),
            "bytes": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
        }

    if manifest_files["jds.jsonl"]["rows"] != manifest_files[
        "sampling_contracts.jsonl"
    ]["rows"]:
        raise ValueError("JD and sampling-contract row counts differ")
    if (
        manifest_files["resumes.jsonl"]["rows"]
        != manifest_files["jds.jsonl"]["rows"] * 3
    ):
        raise ValueError("runtime data does not contain exactly three resumes per JD")

    manifest = {
        "schema_version": "jdmatch_runtime_v1",
        "source_layout": "serialized_v1",
        "files": manifest_files,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare path-independent data files used by jdmatch."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = prepare_runtime_data(args.source, args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
