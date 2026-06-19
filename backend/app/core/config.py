"""Shared path and runtime configuration for the demo backend."""

from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
SAMPLE_DIR = DATA_DIR / "samples"
FRONTEND_DIR = BASE_DIR / "frontend"

USE_LLM = False
DEFAULT_GRAPH_VERSION = "demo-v1"
