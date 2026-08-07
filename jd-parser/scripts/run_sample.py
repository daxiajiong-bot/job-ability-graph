from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jd_parser.batch import BatchOptions, run_batch


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_review_report(input_path: Path, output_dir: Path, report_path: Path) -> None:
    inputs = {row["document_id"]: row for row in _load_jsonl(input_path)}
    cleaned = {row["document_id"]: row for row in _load_jsonl(output_dir / "cleaned.jsonl")}
    validations = {row["document_id"]: row for row in _load_jsonl(output_dir / "validation_results.jsonl")}
    serialized = {row["document_id"]: row for row in _load_jsonl(output_dir / "serialized.jsonl")}

    chunks = ["# JD Parser Manual Review Report", ""]
    for document_id in inputs:
        chunks.extend(
            [
                f"## {document_id}",
                "",
                "### 原始 JD",
                "```text",
                inputs[document_id]["raw_text"],
                "```",
                "",
                "### cleaned_text",
                "```text",
                cleaned.get(document_id, {}).get("cleaned_text", ""),
                "```",
                "",
                "### Profile",
                "```json",
                json.dumps(validations.get(document_id, {}).get("profile"), ensure_ascii=False, indent=2),
                "```",
                "",
                f"### validation 状态\n{validations.get(document_id, {}).get('status', 'missing')}",
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
    input_path = ROOT / "data" / "input" / "sample_12.jsonl"
    output_dir = ROOT / "data" / "output" / "sample_12"
    if output_dir.exists():
        for path in output_dir.glob("*.jsonl"):
            path.unlink()
        summary = output_dir / "summary.json"
        if summary.exists():
            summary.unlink()
    summary = run_batch(BatchOptions(input_path=input_path, output_dir=output_dir, force=True))
    build_review_report(input_path, output_dir, ROOT / "data" / "output" / "sample_12_review.md")
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

