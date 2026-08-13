#!/usr/bin/env python3
"""Collect one internal-only public career-site evaluation snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from trend_discovery.public_eval import DEFAULT_QUOTAS, collect_public_evaluation_snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a rate-limited, auditable evaluation snapshot from official career sites."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/real_eval/snapshots"),
        help="Parent directory; a YYYY-MM-DD child is created.",
    )
    parser.add_argument("--snapshot-date", type=date.fromisoformat)
    parser.add_argument("--keyword", default="大模型")
    parser.add_argument("--delay-seconds", type=float, default=1.1)
    parser.add_argument(
        "--quota",
        action="append",
        default=[],
        metavar="SOURCE=N",
        help="Override a source quota; sources: " + ", ".join(DEFAULT_QUOTAS),
    )
    return parser


def _quotas(values: list[str]) -> dict[str, int]:
    result = dict(DEFAULT_QUOTAS)
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --quota {value!r}; expected SOURCE=N")
        source, raw_count = value.split("=", 1)
        if source not in DEFAULT_QUOTAS:
            raise ValueError(f"unsupported source {source!r}")
        result[source] = int(raw_count)
    return result


def main() -> int:
    args = _parser().parse_args()
    try:
        report = collect_public_evaluation_snapshot(
            args.output_root,
            snapshot_date=args.snapshot_date,
            quotas=_quotas(args.quota),
            keyword=args.keyword,
            delay_seconds=args.delay_seconds,
        )
    except (ValueError, FileExistsError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
