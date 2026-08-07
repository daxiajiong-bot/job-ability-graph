from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _index(path: Path) -> dict[str, dict]:
    return {row["document_id"]: row for row in _load_jsonl(path)}


def build_report(input_path: Path, output_dir: Path, report_path: Path, limit: int) -> None:
    inputs = _load_jsonl(input_path, limit=limit)
    cleaned = _index(output_dir / "cleaned.jsonl")
    validations = _index(output_dir / "validation_results.jsonl")
    serialized = _index(output_dir / "serialized.jsonl")

    chunks = [f"# JD Parser Review Report First {limit}", ""]
    for row in inputs:
        document_id = row["document_id"]
        validation = validations.get(document_id, {})
        chunks.extend(
            [
                f"## {document_id}",
                "",
                "### 原始 JD",
                "```text",
                row.get("raw_text", ""),
                "```",
                "",
                "### cleaned_text",
                "```text",
                cleaned.get(document_id, {}).get("cleaned_text", ""),
                "```",
                "",
                "### Profile",
                "```json",
                json.dumps(validation.get("profile"), ensure_ascii=False, indent=2),
                "```",
                "",
                f"### validation 状态\n{validation.get('status', 'missing')}",
                "",
                "### serialized_text",
                "```text",
                serialized.get(document_id, {}).get("serialized_text", ""),
                "```",
                "",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(chunks), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    build_report(Path(args.input), Path(args.output_dir), Path(args.report), args.limit)
    print(args.report)


if __name__ == "__main__":
    main()

