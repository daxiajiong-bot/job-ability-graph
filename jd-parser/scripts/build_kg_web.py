from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_top_skills(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{"name": row["skill_name"], "count": int(row["mention_count"])} for row in reader]


def _iter_profiles(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _build_skill_index(profiles_path: Path, max_examples: int = 16) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    skill_index: dict[str, dict[str, Any]] = {}
    location_counts: Counter[str] = Counter()
    education_counts: Counter[str] = Counter()
    experience_counts: Counter[str] = Counter()

    for profile in _iter_profiles(profiles_path):
        constraints = profile.get("constraints") or {}
        location = (constraints.get("location") or {}).get("value")
        education = (constraints.get("education") or {}).get("value")
        experience = (constraints.get("experience_years") or {}).get("value")
        if location:
            location_counts[str(location)] += 1
        if education:
            education_counts[str(education)] += 1
        if experience is not None:
            experience_counts[f"{experience}年以上"] += 1

        for skill in profile.get("skills") or []:
            name = str(skill.get("name") or "").strip()
            level = skill.get("level")
            evidence = str(skill.get("evidence") or "").strip()
            if not name or level not in {"required", "preferred", "mentioned"}:
                continue
            item = skill_index.setdefault(
                name,
                {
                    "name": name,
                    "count": 0,
                    "required": 0,
                    "preferred": 0,
                    "mentioned": 0,
                    "jobs": [],
                },
            )
            item["count"] += 1
            item[level] += 1
            if len(item["jobs"]) < max_examples:
                item["jobs"].append(
                    {
                        "document_id": profile.get("document_id"),
                        "title": profile.get("title"),
                        "level": level,
                        "evidence": evidence,
                        "location": location,
                        "education": education,
                        "experience_years": experience,
                    }
                )

    skills = sorted(skill_index.values(), key=lambda row: (-row["count"], row["name"]))
    top_locations = [{"name": name, "count": count} for name, count in location_counts.most_common(25)]
    top_education = [{"name": name, "count": count} for name, count in education_counts.most_common()]
    top_experience = [{"name": name, "count": count} for name, count in experience_counts.most_common()]
    return skills, skill_index, top_locations, top_education, top_experience


def build_web(kg_dir: Path, profiles_path: Path, output_dir: Path) -> dict[str, Any]:
    template_dir = ROOT / "web"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(template_dir, output_dir)

    summary = _read_json(kg_dir / "graph_summary.json")
    validation = _read_json(kg_dir / "validation_report.json")
    top_skills = _read_top_skills(kg_dir / "top_skills.csv")
    sample_graph = _read_json(kg_dir / "sample_subgraph_first_5.json")
    skills, skill_index, top_locations, top_education, top_experience = _build_skill_index(profiles_path)

    payload = {
        "summary": summary,
        "validation": validation,
        "topSkills": top_skills[:50],
        "skills": skills,
        "skillIndex": skill_index,
        "sampleGraph": sample_graph,
        "topLocations": top_locations,
        "topEducation": top_education,
        "topExperience": top_experience,
    }
    data_js = "window.KG_WEB_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    data_path = output_dir / "assets" / "graph-data.js"
    data_path.write_text(data_js, encoding="utf-8")
    return {
        "output_dir": str(output_dir),
        "index": str(output_dir / "index.html"),
        "data_js": str(data_path),
        "skills_indexed": len(skills),
        "sample_nodes": len(sample_graph.get("nodes", [])),
        "sample_edges": len(sample_graph.get("edges", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kg-dir", default=str(ROOT / "data" / "output" / "kg_real_9000"))
    parser.add_argument("--profiles", default=str(ROOT / "data" / "output" / "real_9000" / "profiles.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "data" / "output" / "kg_real_9000" / "web"))
    args = parser.parse_args()
    result = build_web(Path(args.kg_dir), Path(args.profiles), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

