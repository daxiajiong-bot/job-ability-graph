"""Evaluate sample JDs against sample resumes and save Top-k results."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List


## 如果要保存每次匹配产生的 match / graph 中间文件：
## python3 scripts/evaluate_samples.py --save-artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.ingest_service import load_samples
from backend.app.services.match_service import run_match
from backend.app.storage import paths
from backend.app.storage.json_store import save_json, utc_now


def evaluate_samples(top_k: int = 3, save_artifacts: bool = False) -> Dict[str, Any]:
    samples = load_samples()
    jd_samples = samples["jds"]
    resume_samples = samples["resumes"]
    rows: List[Dict[str, Any]] = []
    top1_hits = 0

    for jd in jd_samples:
        ranked = []
        expected = set(jd.get("expected_match_resumes", []))
        for resume in resume_samples:
            result = run_match(
                jd_text=jd["text"],
                resume_text=resume["text"],
                use_llm=False,
                save_artifacts=save_artifacts,
            )
            ranked.append(
                {
                    "resume_id": resume["id"],
                    "resume_name": resume.get("name"),
                    "final_score": result["final_score"],
                    "decision": result["decision"],
                    "matched_skill_count": len(result["matched_skills"]),
                    "missing_skill_count": len(result["missing_skills"]),
                    "partial_skill_count": len(result["partial_skills"]),
                }
            )
        ranked.sort(key=lambda item: (-float(item["final_score"]), item["resume_id"]))
        top1_resume_id = ranked[0]["resume_id"] if ranked else None
        top1_hit = top1_resume_id in expected
        top1_hits += int(top1_hit)
        rows.append(
            {
                "jd_id": jd["id"],
                "jd_title": jd.get("title"),
                "expected_match_resumes": sorted(expected),
                "top1_resume_id": top1_resume_id,
                "top1_hit": top1_hit,
                "top3": ranked[:top_k],
            }
        )

    result = {
        "generated_at": utc_now(),
        "metric": "top1_accuracy",
        "top1_accuracy": round(top1_hits / max(1, len(jd_samples)), 4),
        "jd_count": len(jd_samples),
        "resume_count": len(resume_samples),
        "save_artifacts": save_artifacts,
        "details": rows,
    }
    save_json(paths.EVALUATION_DIR / "evaluation_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate sample JDs against sample resumes."
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top ranked resumes to keep for each JD.",
    )
    parser.add_argument(
        "--save-artifacts",
        action="store_true",
        help="Save match and graph artifacts during evaluation. By default only evaluation_result.json is saved.",
    )
    args = parser.parse_args()

    result = evaluate_samples(top_k=args.top_k, save_artifacts=args.save_artifacts)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
