from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .io_utils import sha256_text


REQUIRED_SECTIONS = {"paths", "models", "analysis", "retrieval", "parsing"}
PACKAGED_DEFAULT_CONFIG = Path(__file__).with_name("default.yaml")


def resolve_config_path(path: str | Path | None = None) -> Path:
    """Resolve an explicit config or the default shipped inside the wheel."""

    if path is not None:
        return Path(path).expanduser().resolve()
    project_default = Path.cwd() / "config" / "default.yaml"
    return project_default.resolve() if project_default.is_file() else PACKAGED_DEFAULT_CONFIG.resolve()


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    value = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{config_path}: expected a YAML mapping")
    if value.get("schema_version") != "jobtrend_config_v1":
        raise ValueError(f"{config_path}: unsupported schema_version")
    missing = sorted(REQUIRED_SECTIONS - set(value))
    if missing:
        raise ValueError(f"{config_path}: missing sections: {missing}")

    config = copy.deepcopy(value)
    root = Path.cwd().resolve() if config_path == PACKAGED_DEFAULT_CONFIG.resolve() else config_path.parent.parent
    for key in ("warehouse", "runs", "qdrant"):
        raw = Path(str(config["paths"][key])).expanduser()
        config["paths"][key] = str(raw.resolve() if raw.is_absolute() else (root / raw).resolve())
    config["_config_path"] = str(config_path)
    config["_root"] = str(root)
    config["_sha256"] = sha256_text(yaml.safe_dump(value, sort_keys=True, allow_unicode=True))
    return config


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in config.items() if not key.startswith("_")}
