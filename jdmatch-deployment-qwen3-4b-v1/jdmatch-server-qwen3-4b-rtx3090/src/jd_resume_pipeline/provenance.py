from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Any, Iterable

import torch

from . import __version__
from .config import config_for_manifest
from .model_registry import read_model_download_manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash(root: Path, paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def collect_provenance(config: dict[str, Any]) -> dict[str, Any]:
    root = Path(config["_root"])
    source_files = list((root / "src/jd_resume_pipeline").glob("*.py"))
    source_files.extend(
        path
        for path in (
            root / "pyproject.toml",
            Path(config["_config_path"]),
        )
        if path.is_file()
    )
    data_dir = Path(config["paths"]["data_dir"])
    runtime_manifest_path = data_dir / "manifest.json"
    runtime_manifest = None
    if runtime_manifest_path.is_file():
        runtime_manifest = json.loads(
            runtime_manifest_path.read_text(encoding="utf-8")
        )
    else:
        runtime_manifest = {
            "schema_version": "computed_at_runtime",
            "files": {
                name: {
                    "bytes": (data_dir / name).stat().st_size,
                    "sha256": _sha256(data_dir / name),
                }
                for name in (
                    "jds.jsonl",
                    "resumes.jsonl",
                    "sampling_contracts.jsonl",
                )
            },
        }
    downloads = read_model_download_manifest(config)
    return {
        "package": {
            "name": "jd-resume-match",
            "version": __version__,
            "source_tree_sha256": _tree_hash(root, source_files),
        },
        "config": config_for_manifest(config),
        "runtime_data": runtime_manifest,
        "models": (
            downloads
            if downloads is not None
            else {
                "schema_version": "model_ids_without_resolved_snapshots",
                "models": {
                    key: config["models"][key]
                    for key in ("embedding", "mining_embedding", "reranker")
                },
                "warning": (
                    "Exact revisions are recorded after "
                    "jdmatch download-models."
                ),
            }
        ),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "torch_cuda_runtime": torch.version.cuda,
            "dependencies": {
                name: _version(name)
                for name in (
                    "transformers",
                    "sentence-transformers",
                    "peft",
                    "accelerate",
                    "huggingface-hub",
                    "numpy",
                    "bitsandbytes",
                    "flash-attn",
                )
            },
        },
    }
