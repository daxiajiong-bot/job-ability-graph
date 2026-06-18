from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .config import OUTPUT_DIR, SOURCES
from .scrapers import fetch_source_records


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def dump_jsonl(path: Path, records: List[dict]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect(keyword: str, target_count: int, output: str | None = None) -> None:
    records: List[dict] = []
    remaining = target_count
    for source in SOURCES:
        if remaining <= 0:
            break
        source_records = fetch_source_records(source, keyword, remaining)
        records.extend([r.model_dump() for r in source_records])
        remaining = target_count - len(records)
    deduped = []
    seen = set()
    for record in records:
        key = (record.get("job_title", ""), record.get("company_name", ""), record.get("location", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    out_path = Path(output) if output else OUTPUT_DIR / "jd_raw.jsonl"
    dump_jsonl(out_path, deduped[:target_count])
    print(f"saved {min(len(deduped), target_count)} records to {out_path}")


def export_samples() -> None:
    ensure_dir(OUTPUT_DIR)
    print(f"output dir: {OUTPUT_DIR}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job-ability-graph")
    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser("collect", help="collect public JD records")
    collect_parser.add_argument("--keyword", default="Python")
    collect_parser.add_argument("--target-count", type=int, default=100)
    collect_parser.add_argument("--output", default=None)

    sub.add_parser("export", help="prepare output dir")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "collect":
        collect(args.keyword, args.target_count, args.output)
    elif args.command == "export":
        export_samples()


if __name__ == "__main__":
    main()
