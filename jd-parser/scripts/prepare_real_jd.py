from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def _load_exclude_ids(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _record_raw_text(record: dict[str, Any]) -> str:
    lines: list[str] = []
    if record.get("job_title"):
        lines.append(f"岗位名称：{record['job_title']}")
    if record.get("location"):
        lines.append(f"工作地点：{record['location']}")
    if record.get("education"):
        lines.append(f"学历要求：{record['education']}")
    if record.get("experience"):
        lines.append(f"经验要求：{record['experience']}")
    if record.get("jd_text"):
        lines.append(str(record["jd_text"]).strip())
    return "\n".join(line for line in lines if line)


def prepare(zip_path: Path, exclude_ids_path: Path, output_path: Path, target_count: int) -> dict[str, Any]:
    exclude_ids = _load_exclude_ids(exclude_ids_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_records = 0
    excluded = 0
    selected = 0
    remaining_after_limit = 0
    seen_excluded: set[str] = set()

    raw_copy_path = output_path.with_name(output_path.stem + "_source_records.jsonl")
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("jd_raw_10000/jd_raw.jsonl") as source, output_path.open("w", encoding="utf-8") as out, raw_copy_path.open("w", encoding="utf-8") as raw_out:
            for raw_line in source:
                total_records += 1
                record = json.loads(raw_line)
                job_id = str(record.get("job_id") or "")
                if job_id in exclude_ids:
                    excluded += 1
                    seen_excluded.add(job_id)
                    continue

                if selected >= target_count:
                    remaining_after_limit += 1
                    continue

                document_id = f"JD_{job_id}" if job_id else f"JD_ROW_{total_records:06d}"
                payload = {
                    "document_id": document_id,
                    "raw_text": _record_raw_text(record),
                    "source": {
                        "job_id": job_id,
                        "source_name": record.get("source_name"),
                        "url": record.get("url"),
                        "original_order": total_records,
                    },
                }
                out.write(json.dumps(payload, ensure_ascii=False) + "\n")
                raw_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                selected += 1

    summary = {
        "zip_path": str(zip_path),
        "exclude_ids_path": str(exclude_ids_path),
        "total_records_in_zip": total_records,
        "exclude_id_count": len(exclude_ids),
        "excluded_records_found": excluded,
        "exclude_ids_missing": len(exclude_ids - seen_excluded),
        "selected_records": selected,
        "target_count": target_count,
        "remaining_not_selected_after_limit": remaining_after_limit,
        "order_policy": "preserve original zip order, exclude sampled job ids, then take the first target_count records",
        "output": str(output_path),
        "source_record_copy": str(raw_copy_path),
    }
    summary_path = output_path.with_name(output_path.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, dest="zip_path")
    parser.add_argument("--exclude-ids", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-count", type=int, default=9000)
    args = parser.parse_args()
    summary = prepare(Path(args.zip_path), Path(args.exclude_ids), Path(args.output), args.target_count)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

