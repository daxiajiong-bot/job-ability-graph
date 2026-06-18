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
