"""Evaluate the first-stage demo against labeled JSON cases.

The evaluator is intentionally separate from the API and matcher internals. It
uses only public functions so the implementation can evolve while the
competition-facing metrics remain stable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.algorithms.pipeline import match_jd_resume, parse_jd, parse_resume

DEFAULT_EVAL_PATH = PROJECT_ROOT / "data" / "evaluation" / "demo_eval_cases.json"
DEFAULT_JD_SAMPLES = PROJECT_ROOT / "data" / "samples" / "jd_samples.json"
DEFAULT_RESUME_SAMPLES = PROJECT_ROOT / "data" / "samples" / "resume_samples.json"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def skill_names(items: Iterable[Mapping[str, Any]]) -> set:
    return {str(item.get("name", "")).strip() for item in items if item.get("name")}


def hit_rate(expected: Sequence[str], actual: Iterable[str]) -> float:
    expected_set = set(expected)
    actual_set = set(actual)
    if not expected_set:
        return 1.0
    return len(expected_set & actual_set) / len(expected_set)


def evaluate_jd_parse(eval_data: Mapping[str, Any], jd_samples: Sequence[Mapping[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    rows = []
    scores = []
    for case in eval_data.get("jd_cases", []):
        sample = jd_samples[int(case["sample_index"])]
        result = parse_jd(sample["text"])
        parsed = result["jd_parse"]
        profile = result["job_profile"]
        actual_skills = skill_names(profile.get("skills", []))
        title_ok = parsed.get("job_title") == case["expected_title"]
        category_ok = parsed.get("job_category") == case["expected_category"]
        skills_score = hit_rate(case.get("expected_min_skills", []), actual_skills)
        score = (float(title_ok) + float(category_ok) + skills_score) / 3
        scores.append(score)
        rows.append(
            {
                "id": case["id"],
                "score": round(score, 3),
                "title_ok": title_ok,
                "category_ok": category_ok,
                "skill_hit_rate": round(skills_score, 3),
                "missing_expected_skills": sorted(set(case.get("expected_min_skills", [])) - actual_skills),
            }
        )
    return average(scores), rows


def evaluate_resume_parse(
    eval_data: Mapping[str, Any],
    resume_samples: Sequence[Mapping[str, Any]],
) -> Tuple[float, List[Dict[str, Any]]]:
    rows = []
    scores = []
    for case in eval_data.get("resume_cases", []):
        sample = resume_samples[int(case["sample_index"])]
        result = parse_resume(sample["text"])
        parsed = result["resume_parse"]
        profile = result["resume_profile"]
        actual_skills = skill_names(profile.get("skills", []))
        candidate_ok = parsed.get("candidate_id") == case["expected_candidate"]
        education_ok = parsed.get("education") == case["expected_education"]
        skills_score = hit_rate(case.get("expected_min_skills", []), actual_skills)
        score = (float(candidate_ok) + float(education_ok) + skills_score) / 3
        scores.append(score)
        rows.append(
            {
                "id": case["id"],
                "score": round(score, 3),
                "candidate_ok": candidate_ok,
                "education_ok": education_ok,
                "skill_hit_rate": round(skills_score, 3),
                "missing_expected_skills": sorted(set(case.get("expected_min_skills", [])) - actual_skills),
            }
        )
    return average(scores), rows


def evaluate_matching(
    eval_data: Mapping[str, Any],
    jd_samples: Sequence[Mapping[str, Any]],
    resume_samples: Sequence[Mapping[str, Any]],
) -> Tuple[float, List[Dict[str, Any]]]:
    jd_by_id = {item["id"]: item for item in jd_samples}
    resume_by_id = {item["id"]: item for item in resume_samples}
    rows = []
    successes = []
    for case in eval_data.get("match_cases", []):
        jd = jd_by_id[case["jd_id"]]
        candidate_ids = [case["positive_resume_id"], *case.get("negative_resume_ids", [])]
        scores = []
        for resume_id in candidate_ids:
            resume = resume_by_id[resume_id]
            result = match_jd_resume(jd["text"], resume["text"])
            scores.append({"resume_id": resume_id, "score": result["match_result"]["final_score"]})
        scores.sort(key=lambda item: item["score"], reverse=True)
        top_resume_id = scores[0]["resume_id"] if scores else None
        success = top_resume_id == case["positive_resume_id"]
        successes.append(float(success))
        rows.append(
            {
                "jd_id": case["jd_id"],
                "positive_resume_id": case["positive_resume_id"],
                "top_resume_id": top_resume_id,
                "success": success,
                "ranked_scores": scores,
            }
        )
    return average(successes), rows


def average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def evaluate(eval_path: Path, jd_samples_path: Path, resume_samples_path: Path) -> Dict[str, Any]:
    eval_data = load_json(eval_path)
    jd_samples = load_json(jd_samples_path)
    resume_samples = load_json(resume_samples_path)

    jd_accuracy, jd_rows = evaluate_jd_parse(eval_data, jd_samples)
    resume_accuracy, resume_rows = evaluate_resume_parse(eval_data, resume_samples)
    match_accuracy, match_rows = evaluate_matching(eval_data, jd_samples, resume_samples)

    targets = eval_data.get("metadata", {})
    return {
        "dataset": {
            "eval_path": str(eval_path),
            "jd_cases": len(eval_data.get("jd_cases", [])),
            "resume_cases": len(eval_data.get("resume_cases", [])),
            "match_cases": len(eval_data.get("match_cases", [])),
        },
        "metrics": {
            "jd_parse_accuracy": round(jd_accuracy, 4),
            "resume_parse_accuracy": round(resume_accuracy, 4),
            "match_accuracy": round(match_accuracy, 4),
        },
        "targets": {
            "jd_parse_accuracy": targets.get("target_jd_parse_accuracy", 0.9),
            "resume_parse_accuracy": targets.get("target_resume_parse_accuracy", 0.9),
            "match_accuracy": targets.get("target_match_accuracy", 0.9),
        },
        "passes_targets": {
            "jd_parse_accuracy": jd_accuracy >= float(targets.get("target_jd_parse_accuracy", 0.9)),
            "resume_parse_accuracy": resume_accuracy >= float(targets.get("target_resume_parse_accuracy", 0.9)),
            "match_accuracy": match_accuracy >= float(targets.get("target_match_accuracy", 0.9)),
        },
        "details": {
            "jd_parse": jd_rows,
            "resume_parse": resume_rows,
            "matching": match_rows,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the first-stage demo.")
    parser.add_argument("--eval", default=str(DEFAULT_EVAL_PATH), help="Path to evaluation case JSON.")
    parser.add_argument("--jd-samples", default=str(DEFAULT_JD_SAMPLES), help="Path to JD sample JSON.")
    parser.add_argument("--resume-samples", default=str(DEFAULT_RESUME_SAMPLES), help="Path to resume sample JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    result = evaluate(Path(args.eval), Path(args.jd_samples), Path(args.resume_samples))
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
