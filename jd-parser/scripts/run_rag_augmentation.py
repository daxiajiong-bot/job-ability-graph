from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jd_parser.rag import run_rag_augmentation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", default=str(ROOT / "data" / "output" / "real_9000" / "profiles.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "output" / "rag_real_9000"))
    parser.add_argument("--max-additions", type=int, default=20)
    args = parser.parse_args()
    summary = run_rag_augmentation(Path(args.profiles), Path(args.output_dir), max_additions=args.max_additions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

