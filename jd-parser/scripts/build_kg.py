from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jd_parser.kg import build_graph


def main() -> None:
    profiles = ROOT / "data" / "output" / "real_9000" / "profiles.jsonl"
    output = ROOT / "data" / "output" / "kg_real_9000"
    summary = build_graph(profiles, output, sample_jobs=5)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

