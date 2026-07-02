#!/usr/bin/env python3
"""Run a small real-Ollama profile extraction preview over raw JD/resume data."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.domain.entities import DocumentType  # noqa: E402
from backend.app.infrastructure.wiring import build_container  # noqa: E402


JD_RAW_PATH = REPO_ROOT / "data" / "small-raw" / "jd_raw.jsonl"
RESUME_RAW_PATH = REPO_ROOT / "data" / "small-raw" / "resume_raw.jsonl"
OUTPUT_ROOT = REPO_ROOT / "data" / "structured" / "profiles" / "raw_preview_20260630"
SUMMARY_PATH = OUTPUT_ROOT / "summary.json"
SAMPLE_LIMIT = 10


def main() -> int:
    _configure_ollama_env()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    container = build_container(
        data_governance_root=str(REPO_ROOT / "data"),
        profile_artifact_root=str(OUTPUT_ROOT),
    )
    jd_rows = _read_jsonl(JD_RAW_PATH, SAMPLE_LIMIT)
    resume_rows = _read_jsonl(RESUME_RAW_PATH, SAMPLE_LIMIT)

    results: list[dict[str, Any]] = []
    print(f"Running profile preview with {len(jd_rows)} JD rows and {len(resume_rows)} resume rows.", flush=True)
    print(f"Artifacts: {OUTPUT_ROOT}", flush=True)

    for index, row in enumerate(jd_rows, start=1):
        result = _run_jd(container.facade, index, row)
        results.append(result)
        _print_result(result)

    for index, row in enumerate(resume_rows, start=1):
        result = _run_resume(container.facade, index, row)
        results.append(result)
        _print_result(result)

    summary = {
        "schema_version": "profile-preview/v1",
        "sample_limit": SAMPLE_LIMIT,
        "raw_inputs": {
            "jd": str(JD_RAW_PATH),
            "resume": str(RESUME_RAW_PATH),
        },
        "output_root": str(OUTPUT_ROOT),
        "counts": _counts(results),
        "records": results,
        "examples": _examples(results),
    }
    _write_json(SUMMARY_PATH, summary)
    _print_summary(summary)
    return 0


def _configure_ollama_env() -> None:
    defaults = {
        "LLM_BACKEND": "ollama",
        "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
        "LLM_API_KEY": "ollama",
        "LLM_MODEL": "qwen2.5:7b",
        "LLM_TIMEOUT_SECONDS": "120",
        "LLM_MAX_INPUT_CHARS": "12000",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    for key, value in defaults.items():
        os.environ[key] = value


def _read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


def _run_jd(facade: Any, index: int, row: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(row.get("job_id") or f"jd-{index:02d}")
    print(f"Processing jd #{index:02d} raw_id={raw_id}", flush=True)
    document = facade.create_document(
        DocumentType.JD,
        _jd_text(row),
        {
            "source_system": str(row.get("source_name") or "small-raw"),
            "external_id": raw_id,
            "uri": row.get("url"),
            "published_at": row.get("publish_date"),
        },
        {"raw_index": index, "raw_file": str(JD_RAW_PATH), "raw_type": "jd"},
    )
    profile = facade.create_job_profile(document["id"])
    return _profile_result("jd", index, raw_id, document, profile)


def _run_resume(facade: Any, index: int, row: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(row.get("resume_id") or f"resume-{index:02d}")
    print(f"Processing resume #{index:02d} raw_id={raw_id}", flush=True)
    document = facade.create_document(
        DocumentType.RESUME,
        _resume_text(row),
        {
            "source_system": "small-raw",
            "external_id": raw_id,
            "uri": row.get("target_url"),
        },
        {
            "raw_index": index,
            "raw_file": str(RESUME_RAW_PATH),
            "raw_type": "resume",
            "target_job_id": row.get("target_job_id"),
            "privacy_level": row.get("privacy_level"),
        },
    )
    profile = facade.create_candidate_profile(document["id"])
    return _profile_result("resume", index, raw_id, document, profile)


def _jd_text(row: dict[str, Any]) -> str:
    sections = [
        f"岗位名称：{_text(row.get('job_title'))}",
        f"公司名称：{_text(row.get('company_name'))}",
        f"行业：{_text(row.get('industry'))}",
        f"地点：{_text(row.get('location'))}",
        f"薪资下限：{_text(row.get('salary_min'))}",
        f"薪资上限：{_text(row.get('salary_max'))}",
        f"经验要求：{_text(row.get('experience'))}",
        f"学历要求：{_text(row.get('education'))}",
        f"发布时间：{_text(row.get('publish_date'))}",
        f"技能标准列表：{_join(row.get('skills_norm'))}",
        "JD原文：",
        _text(row.get("jd_text")),
    ]
    return "\n".join(section for section in sections if section.strip())


def _resume_text(row: dict[str, Any]) -> str:
    sections = [
        _text(row.get("resume_text")),
        f"目标岗位：{_text(row.get('target_job_title'))}",
        f"目标公司：{_text(row.get('target_company_name'))}",
        f"目标行业：{_text(row.get('target_industry'))}",
        f"目标地点：{_text(row.get('target_location'))}",
        f"当前角色：{_text(row.get('current_role'))}",
        f"教育背景：{_text(row.get('education'))}",
        f"工作年限：{_text(row.get('experience_years'))}",
        f"核心技能：{_join(row.get('skills'))}",
        f"匹配技能种子：{_join(row.get('matched_skills_seed'))}",
        f"缺失技能种子：{_join(row.get('missing_skills_seed'))}",
        "项目经历：",
        _json_inline(row.get("projects")),
        "工作经历：",
        _json_inline(row.get("work_experience")),
    ]
    return "\n".join(section for section in sections if section.strip())


def _profile_result(
    record_type: str,
    index: int,
    raw_id: str,
    document: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    attributes = profile.get("attributes", {})
    profile_key = "jd_profile" if record_type == "jd" else "resume_profile"
    profile_body = attributes.get(profile_key, {})
    return {
        "record_type": record_type,
        "raw_index": index,
        "raw_id": raw_id,
        "document_id": document.get("id"),
        "profile_id": profile.get("id"),
        "state": profile.get("state"),
        "implementation": profile.get("implementation"),
        "warnings": profile.get("warnings", []),
        "skill_count": len(attributes.get("skills") or []),
        "evidence_count": len(profile.get("evidence") or []),
        "artifact_path": (profile.get("artifacts") or {}).get("profile_json"),
        "profile_schema": attributes.get("profile_schema"),
        "profile_keys": sorted(profile_body.keys()) if isinstance(profile_body, dict) else [],
    }


def _counts(results: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "total": len(results),
        "available": sum(1 for result in results if result["state"] == "available"),
        "not_implemented": sum(1 for result in results if result["state"] == "not_implemented"),
        "by_type": {},
    }
    for record_type in ["jd", "resume"]:
        typed = [result for result in results if result["record_type"] == record_type]
        output["by_type"][record_type] = {
            "total": len(typed),
            "available": sum(1 for result in typed if result["state"] == "available"),
            "not_implemented": sum(1 for result in typed if result["state"] == "not_implemented"),
        }
    return output


def _examples(results: list[dict[str, Any]]) -> dict[str, Any]:
    examples: dict[str, Any] = {}
    for record_type in ["jd", "resume"]:
        result = next(
            (
                item
                for item in results
                if item["record_type"] == record_type and item.get("state") == "available" and item.get("artifact_path")
            ),
            None,
        )
        if result is None:
            continue
        artifact_path = Path(str(result["artifact_path"]))
        if not artifact_path.exists():
            continue
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        profile = artifact.get("profile", {})
        attributes = profile.get("attributes", {})
        if record_type == "jd":
            jd_profile = attributes.get("jd_profile", {})
            examples[record_type] = {
                "artifact_path": str(artifact_path),
                "job": jd_profile.get("job"),
                "skills": jd_profile.get("skills", []),
                "evidence": profile.get("evidence", []),
            }
        else:
            resume_profile = attributes.get("resume_profile", {})
            examples[record_type] = {
                "artifact_path": str(artifact_path),
                "career_intent": resume_profile.get("career_intent"),
                "skills": resume_profile.get("skills", []),
                "evidence": profile.get("evidence", []),
            }
    return examples


def _print_result(result: dict[str, Any]) -> None:
    print(
        f"[{result['record_type']} #{result['raw_index']:02d}] "
        f"raw_id={result['raw_id']} state={result['state']} "
        f"implementation={result['implementation']} artifact={result.get('artifact_path')}",
        flush=True,
    )
    if result["state"] == "not_implemented":
        for warning in result.get("warnings", []):
            print(f"  warning: {warning}", flush=True)


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nSummary", flush=True)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2), flush=True)
    print(f"summary_json={SUMMARY_PATH}", flush=True)
    for record_type, example in summary["examples"].items():
        print(f"\nExample {record_type}: {example['artifact_path']}", flush=True)
        if record_type == "jd":
            print("job:", flush=True)
            print(json.dumps(example["job"], ensure_ascii=False, indent=2), flush=True)
        else:
            print("career_intent:", flush=True)
            print(json.dumps(example["career_intent"], ensure_ascii=False, indent=2), flush=True)
        print("skills:", flush=True)
        print(json.dumps(example["skills"], ensure_ascii=False, indent=2), flush=True)
        print("evidence:", flush=True)
        print(json.dumps(example["evidence"], ensure_ascii=False, indent=2), flush=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(_text(item) for item in value if _text(item))
    return _text(value)


def _json_inline(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


if __name__ == "__main__":
    raise SystemExit(main())
