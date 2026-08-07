from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


REQUIRED_SECTIONS = {
    "paths",
    "models",
    "hardware",
    "text",
    "sampling",
    "training",
    "evaluation",
}


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{config_path}: expected a YAML mapping")
    missing = sorted(REQUIRED_SECTIONS - set(value))
    if missing:
        raise ValueError(f"{config_path}: missing config sections: {missing}")
    if value.get("schema_version") != "jdmatch_config_v1":
        raise ValueError(f"{config_path}: unsupported schema_version")

    config = copy.deepcopy(value)
    root = config_path.parent.parent
    config["_config_path"] = str(config_path)
    config["_root"] = str(root)
    for key in ("data_dir", "run_dir"):
        raw = Path(str(config["paths"][key])).expanduser()
        config["paths"][key] = str(
            raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        )
    return config


def config_for_manifest(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in config.items()
        if not key.startswith("_")
    }

