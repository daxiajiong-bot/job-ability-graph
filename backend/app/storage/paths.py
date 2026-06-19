"""Centralized data paths for JSON demo artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.app.core.config import DATA_DIR


RAW_DIR = DATA_DIR / "raw"
RAW_JD_DIR = RAW_DIR / "jd"
RAW_RESUME_DIR = RAW_DIR / "resume"
PARSED_DIR = DATA_DIR / "parsed"
PARSED_JD_PROFILES_DIR = PARSED_DIR / "jd_profiles"
PARSED_RESUME_PROFILES_DIR = PARSED_DIR / "resume_profiles"
NORMALIZED_DIR = DATA_DIR / "normalized"
EVIDENCE_DIR = DATA_DIR / "evidence"
MATCHES_DIR = DATA_DIR / "matches"
GRAPH_DIR = DATA_DIR / "graph"
EVALUATION_DIR = DATA_DIR / "evaluation"
SAMPLES_DIR = DATA_DIR / "samples"


DATA_DIRECTORIES = (
    RAW_DIR,
    RAW_JD_DIR,
    RAW_RESUME_DIR,
    PARSED_DIR,
    PARSED_JD_PROFILES_DIR,
    PARSED_RESUME_PROFILES_DIR,
    NORMALIZED_DIR,
    EVIDENCE_DIR,
    MATCHES_DIR,
    GRAPH_DIR,
    EVALUATION_DIR,
    SAMPLES_DIR,
)


def ensure_data_dirs(extra_dirs: Iterable[Path] = ()) -> None:
    for directory in (*DATA_DIRECTORIES, *tuple(extra_dirs)):
        directory.mkdir(parents=True, exist_ok=True)


ensure_data_dirs()


def get_normalized_path(text_hash: str, prefix: str = "jd") -> Path:
    """获取标准化数据的文件路径"""
    filename = f"{prefix}_{text_hash}.json"
    return NORMALIZED_DIR / filename


def get_match_path(jd_id: str, resume_id: str) -> Path:
    """获取匹配结果的文件路径"""
    safe_jd_id = jd_id.replace("/", "_").replace("\\", "_")
    safe_resume_id = resume_id.replace("/", "_").replace("\\", "_")
    filename = f"match_{safe_jd_id}_{safe_resume_id}.json"
    return MATCHES_DIR / filename


def get_graph_path(match_id: str) -> Path:
    """获取图谱数据的文件路径"""
    filename = f"graph_{match_id}.json"
    return GRAPH_DIR / filename
