from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jd_parser.extraction_eval import evaluate_extraction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", default=str(ROOT / "data" / "output" / "real_9000" / "profiles.jsonl"))
    parser.add_argument("--validation-results", default=str(ROOT / "data" / "output" / "real_9000" / "validation_results.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "output" / "extraction_eval_real_9000"))
    args = parser.parse_args()

    report = evaluate_extraction(
        profiles_path=Path(args.profiles),
        validation_results_path=Path(args.validation_results),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(json.dumps(report["rag_recommendation"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

