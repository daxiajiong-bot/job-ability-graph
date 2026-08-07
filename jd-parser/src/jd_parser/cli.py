from __future__ import annotations

import argparse
from pathlib import Path

from .batch import BatchOptions, run_batch
from .kg import build_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jd-parser")
    sub = parser.add_subparsers(dest="command", required=True)

    batch = sub.add_parser("batch", help="run JSONL batch extraction")
    batch.add_argument("--input", required=True)
    batch.add_argument("--output", required=True)
    batch.add_argument("--force", action="store_true")
    batch.add_argument("--retry-status", action="append", default=[])

    kg = sub.add_parser("kg", help="build knowledge graph from profiles.jsonl")
    kg.add_argument("--profiles", required=True)
    kg.add_argument("--output", required=True)
    kg.add_argument("--sample-jobs", type=int, default=5)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "batch":
        summary = run_batch(
            BatchOptions(
                input_path=Path(args.input),
                output_dir=Path(args.output),
                force=args.force,
                retry_statuses=set(args.retry_status),
            )
        )
        print(summary.model_dump_json(indent=2))
    elif args.command == "kg":
        summary = build_graph(Path(args.profiles), Path(args.output), sample_jobs=args.sample_jobs)
        import json

        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
