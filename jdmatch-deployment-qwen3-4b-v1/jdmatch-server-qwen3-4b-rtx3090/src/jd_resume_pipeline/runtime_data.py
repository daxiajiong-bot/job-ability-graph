from __future__ import annotations

import glob
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .io_utils import read_jsonl, write_jsonl


EXPECTED_SLOTS = {"P1", "P2", "H1"}
_YEAR_RE = re.compile(r"(?<!\d)(\d{1,2})(?:\s*年|年\+|\+年)")
_WORK_START_RE = re.compile(r"工作经历\d*[：:](\d{4})-(\d{2})")
_DEGREE_ORDER = {"不限": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def _batch_request_paths(root: Path) -> list[Path]:
    patterns = [
        "data/batches/input/resumes_structured_direct_v2_1_canary_200.submit.jsonl",
        "data/batches/input/resumes_structured_direct_v2_1_full/shard_*.submit.jsonl",
        "data/batches/input/resumes_structured_direct_v2_1_completion/shard_*.submit.jsonl",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(item) for item in glob.glob(str(root / pattern)))
    return sorted(paths)


def extract_sampling_contracts(
    root: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    clean_jds = {
        str(row["jd_id"]): row
        for row in read_jsonl(root / "data/clean/jd_clean.jsonl")
    }
    contracts: dict[str, dict[str, Any]] = {}
    request_paths = _batch_request_paths(root)
    if not request_paths:
        raise ValueError("no structured resume Batch request files found")

    for path in request_paths:
        for row in read_jsonl(path):
            content = row["body"]["messages"][1]["content"]
            envelope = json.loads(str(content).split("\n", 1)[1])
            authoritative = envelope["authoritative_input"]
            contract = authoritative["generation_contract"]
            jd_id = str(authoritative["jd_id"])
            source = clean_jds.get(jd_id)
            if source is None:
                raise ValueError(f"{jd_id}: contract has no clean JD")
            value = {
                "jd_id": jd_id,
                "split": source["split"],
                "near_dup_cluster_id": source["near_dup_cluster_id"],
                "job_family_proxy": source.get("job_family_proxy"),
                "education": source.get("education"),
                "experience": source.get("experience"),
                "omitted_requirement_id": contract["omitted_requirement_id"],
                "omitted_requirement_text": contract[
                    "omitted_requirement_text"
                ],
                "h1_forbidden_terms": contract["h1_forbidden_terms"],
                "positive_evidence_groups": contract[
                    "positive_evidence_groups"
                ],
                "core_requirement_ids": contract["core_requirement_ids"],
                "preferred_requirement_ids": contract[
                    "preferred_requirement_ids"
                ],
            }
            previous = contracts.get(jd_id)
            if previous is not None and previous != value:
                raise ValueError(f"{jd_id}: conflicting generation contracts")
            contracts[jd_id] = value

    missing = sorted(set(clean_jds) - set(contracts))
    extra = sorted(set(contracts) - set(clean_jds))
    if missing or extra:
        raise ValueError(
            f"contract coverage mismatch: missing={missing[:10]}, extra={extra[:10]}"
        )
    result = [contracts[jd_id] for jd_id in sorted(contracts)]
    write_jsonl(output_path, result)
    return result


def load_runtime_data(data_dir: str | Path) -> dict[str, Any]:
    root = Path(data_dir)
    required = {
        "jds": root / "jds.jsonl",
        "resumes": root / "resumes.jsonl",
        "contracts": root / "sampling_contracts.jsonl",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise ValueError(f"runtime data files are missing: {missing}")

    jds = list(read_jsonl(required["jds"]))
    resumes = list(read_jsonl(required["resumes"]))
    contracts = list(read_jsonl(required["contracts"]))
    jd_by_id = {str(row["id"]): row for row in jds}
    resume_by_id = {str(row["id"]): row for row in resumes}
    contract_by_id = {str(row["jd_id"]): row for row in contracts}
    if len(jd_by_id) != len(jds):
        raise ValueError("duplicate JD IDs in runtime data")
    if len(resume_by_id) != len(resumes):
        raise ValueError("duplicate resume IDs in runtime data")
    if set(jd_by_id) != set(contract_by_id):
        raise ValueError("JD/contract identity mismatch")

    resumes_by_jd: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for resume in resumes:
        jd_id = str(resume["source_jd_id"])
        if jd_id not in jd_by_id:
            raise ValueError(f"{resume['id']}: unknown source JD")
        if resume["split"] != jd_by_id[jd_id]["split"]:
            raise ValueError(f"{resume['id']}: split mismatch")
        resumes_by_jd[jd_id].append(resume)
    for jd_id, values in resumes_by_jd.items():
        slots = {str(row["metadata"]["slot"]) for row in values}
        if slots != EXPECTED_SLOTS:
            raise ValueError(f"{jd_id}: incomplete resume triplet")

    return {
        "jds": jds,
        "resumes": resumes,
        "contracts": contracts,
        "jd_by_id": jd_by_id,
        "resume_by_id": resume_by_id,
        "contract_by_id": contract_by_id,
        "resumes_by_jd": dict(resumes_by_jd),
    }


def rows_for_split(
    rows: Iterable[dict[str, Any]],
    split: str,
) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("split")) == split]


def degree_from_resume(text: str) -> str | None:
    education = text.rsplit("\n教育：", 1)[-1]
    for degree in ("博士", "硕士", "本科", "大专"):
        if degree in education:
            return degree
    return None


def experience_years_from_resume(
    text: str,
    reference_year: int = 2026,
    reference_month: int = 7,
) -> float | None:
    summary = text.splitlines()[0] if text else ""
    years = [int(item) for item in _YEAR_RE.findall(summary)]
    if years:
        return float(max(years))
    starts = [(int(y), int(m)) for y, m in _WORK_START_RE.findall(text)]
    if not starts:
        return None
    year, month = min(starts)
    return max(0.0, ((reference_year - year) * 12 + reference_month - month) / 12)


def minimum_experience_years(value: Any) -> float | None:
    text = str(value or "")
    match = re.search(r"(\d+)", text)
    return float(match.group(1)) if match else None


def violates_hard_constraints(
    contract: dict[str, Any],
    resume_text: str,
) -> list[str]:
    reasons: list[str] = []
    target_degree = str(contract.get("education") or "")
    candidate_degree = degree_from_resume(resume_text)
    if target_degree in _DEGREE_ORDER and candidate_degree in _DEGREE_ORDER:
        if _DEGREE_ORDER[candidate_degree] < _DEGREE_ORDER[target_degree]:
            reasons.append("education_below_requirement")
    target_years = minimum_experience_years(contract.get("experience"))
    candidate_years = experience_years_from_resume(resume_text)
    if (
        target_years is not None
        and candidate_years is not None
        and candidate_years + 0.01 < target_years
    ):
        reasons.append("experience_below_requirement")
    return reasons
