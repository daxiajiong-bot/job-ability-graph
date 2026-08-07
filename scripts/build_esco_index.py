#!/usr/bin/env python3
"""Build a local ESCO index from the official CSV snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.data_governance.esco import DEFAULT_ESCO_VERSION, build_esco_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/esco index from an official ESCO CSV directory or zip.")
    parser.add_argument("--source", required=True, help="Path to official ESCO CSV directory or zip file.")
    parser.add_argument("--output-root", default="data/esco", help="Output ESCO index root.")
    parser.add_argument("--version", default=DEFAULT_ESCO_VERSION, help="ESCO version label.")
    args = parser.parse_args()

    manifest = build_esco_index(Path(args.source), Path(args.output_root), version=args.version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
