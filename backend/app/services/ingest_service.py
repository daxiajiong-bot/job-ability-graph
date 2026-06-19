"""Sample and input loading service."""

from __future__ import annotations

import json
from typing import Any, Dict

from backend.app.core.config import SAMPLE_DIR


def load_samples() -> Dict[str, Any]:
    with (SAMPLE_DIR / "jd_samples.json").open(encoding="utf-8") as file:
        jds = json.load(file)
    with (SAMPLE_DIR / "resume_samples.json").open(encoding="utf-8") as file:
        resumes = json.load(file)
    return {"jds": jds, "resumes": resumes}
