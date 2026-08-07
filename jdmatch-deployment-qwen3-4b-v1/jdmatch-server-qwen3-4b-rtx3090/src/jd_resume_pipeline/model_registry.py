from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

from .io_utils import write_json


MODEL_KEYS = ("embedding", "mining_embedding", "reranker")


def model_download_manifest_path(config: dict[str, Any]) -> Path:
    return Path(config["paths"]["run_dir"]) / "model_downloads.json"


def download_models(config: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    resolved: dict[tuple[str, str | None], dict[str, str]] = {}
    for key in MODEL_KEYS:
        model_id = str(config["models"][key])
        revision_value = config["models"].get(f"{key}_revision")
        requested_revision = (
            str(revision_value) if revision_value is not None else None
        )
        identity = (model_id, requested_revision)
        if identity not in resolved:
            path = Path(
                snapshot_download(
                    repo_id=model_id,
                    revision=requested_revision,
                )
            ).resolve()
            resolved[identity] = {
                "model_id": model_id,
                "requested_revision": requested_revision or "main",
                "resolved_revision": path.name,
                "snapshot_path": str(path),
            }
        entries.append({"key": key, **resolved[identity]})
    payload: dict[str, Any] = {
        "schema_version": "jdmatch_model_downloads_v1",
        "status": "downloaded",
        "models": entries,
    }
    write_json(model_download_manifest_path(config), payload)
    return payload


def read_model_download_manifest(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    path = model_download_manifest_path(config)
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != "jdmatch_model_downloads_v1":
        raise ValueError(f"{path}: unsupported model manifest")
    return value


def resolve_model_source(config: dict[str, Any], key: str) -> str:
    if key not in MODEL_KEYS:
        raise ValueError(f"unknown model key: {key}")
    model_id = str(config["models"][key])
    manifest = read_model_download_manifest(config)
    if manifest is not None:
        for entry in manifest["models"]:
            if entry["key"] != key:
                continue
            if entry["model_id"] != model_id:
                raise ValueError(
                    f"downloaded model for {key} is {entry['model_id']}, "
                    f"but config requests {model_id}"
                )
            snapshot = Path(entry["snapshot_path"])
            if not snapshot.is_dir():
                raise ValueError(
                    f"downloaded snapshot is missing: {snapshot}; "
                    "rerun jdmatch download-models"
                )
            return str(snapshot)
    return model_id
