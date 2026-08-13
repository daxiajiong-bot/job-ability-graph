#!/usr/bin/env python3
"""Validate a collected real evaluation snapshot without claiming gold metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trend_discovery.public_eval import (
    summarize_authoritative_corpus,
    validate_evaluation_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--warehouse", type=Path)
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--authoritative-warehouse",
        type=Path,
        help="Optionally emit a text-free policy/report readiness index.",
    )
    parser.add_argument(
        "--authoritative-output",
        type=Path,
        help="Defaults to SNAPSHOT_DIR/shareable.",
    )
    args = parser.parse_args()
    report = validate_evaluation_snapshot(
        args.snapshot_dir,
        warehouse_dir=args.warehouse,
        analysis_dir=args.analysis,
        output_path=args.output,
    )
    output: dict[str, object] = {"snapshot": report}
    if args.authoritative_warehouse:
        output["authoritative_corpus"] = summarize_authoritative_corpus(
            args.authoritative_warehouse,
            args.authoritative_output or args.snapshot_dir / "shareable",
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "structural_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
