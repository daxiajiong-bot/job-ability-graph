from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NODE_LABELS = {
    "Job",
    "Skill",
    "Evidence",
    "Education",
    "ExperienceRequirement",
    "Location",
}

RELATION_TYPES = {
    "REQUIRES_SKILL",
    "PREFERS_SKILL",
    "MENTIONS_SKILL",
    "SUPPORTED_BY",
    "REQUIRES_EDUCATION",
    "REQUIRES_EXPERIENCE",
    "LOCATED_IN",
}

SKILL_RELATION_BY_LEVEL = {
    "required": "REQUIRES_SKILL",
    "preferred": "PREFERS_SKILL",
    "mentioned": "MENTIONS_SKILL",
}


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _compact_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _node_id(label: str, value: str) -> str:
    return f"{label.lower()}:{_hash(value)}"


def _evidence_id(document_id: str, evidence: str) -> str:
    return f"evidence:{document_id}:{_hash(evidence)}"


def _edge_id(source_id: str, relation_type: str, target_id: str, marker: str) -> str:
    return f"edge:{_hash('|'.join([source_id, relation_type, target_id, marker]), 16)}"


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_profiles(path: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                profiles.append(json.loads(line))
    return profiles


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def add_node(self, node_id: str, label: str, properties: dict[str, Any]) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"node_id": node_id, "label": label, "properties": properties}

    def add_edge(
        self,
        source_id: str,
        relation_type: str,
        target_id: str,
        marker: str,
        properties: dict[str, Any],
    ) -> None:
        edge_id = _edge_id(source_id, relation_type, target_id, marker)
        if edge_id not in self.edges:
            self.edges[edge_id] = {
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "properties": properties,
            }

    def add_evidence(self, document_id: str, evidence: str, source_field: str) -> str:
        evidence_text = _compact_text(evidence)
        evidence_id = _evidence_id(document_id, evidence_text)
        self.add_node(
            evidence_id,
            "Evidence",
            {
                "evidence_id": evidence_id,
                "document_id": document_id,
                "text": evidence_text,
                "source_field": source_field,
            },
        )
        return evidence_id


def build_graph(profiles_path: Path, output_dir: Path, sample_jobs: int = 5) -> dict[str, Any]:
    profiles = _read_profiles(profiles_path)
    builder = GraphBuilder()
    raw_text_by_document: dict[str, str] = {}
    job_skill_counts: Counter[str] = Counter()
    skill_counter: Counter[str] = Counter()
    level_counter: Counter[str] = Counter()

    for profile in profiles:
        document_id = profile["document_id"]
        raw_text_by_document[document_id] = profile.get("raw_text", "")
        constraints = profile.get("constraints") or {}
        education = constraints.get("education") or {}
        experience = constraints.get("experience_years") or {}
        location = constraints.get("location") or {}

        job_id = f"job:{document_id}"
        builder.add_node(
            job_id,
            "Job",
            {
                "document_id": document_id,
                "title": profile.get("title"),
                "education": education.get("value"),
                "experience_years": experience.get("value"),
                "location": location.get("value"),
            },
        )

        for index, skill in enumerate(profile.get("skills") or [], start=1):
            skill_name = _compact_text(skill.get("name"))
            evidence = _compact_text(skill.get("evidence"))
            level = skill.get("level")
            if not skill_name or level not in SKILL_RELATION_BY_LEVEL:
                continue

            skill_id = _node_id("skill", skill_name)
            evidence_id = builder.add_evidence(document_id, evidence, "skills")
            relation_type = SKILL_RELATION_BY_LEVEL[level]

            builder.add_node(
                skill_id,
                "Skill",
                {
                    "name": skill_name,
                    "surface_form_policy": "exact text surface with whitespace compacted; no skill normalization",
                },
            )
            builder.add_edge(
                job_id,
                relation_type,
                skill_id,
                f"{document_id}:skill:{index}:{evidence_id}",
                {
                    "document_id": document_id,
                    "level": level,
                    "evidence_id": evidence_id,
                    "evidence": evidence,
                    "occurrence_index": index,
                },
            )
            builder.add_edge(
                skill_id,
                "SUPPORTED_BY",
                evidence_id,
                f"{document_id}:skill-evidence:{index}",
                {"document_id": document_id, "evidence_id": evidence_id},
            )
            job_skill_counts[document_id] += 1
            skill_counter[skill_name] += 1
            level_counter[level] += 1

        if education.get("value"):
            value = _compact_text(education.get("value"))
            evidence_text = _compact_text(education.get("evidence"))
            node_id = _node_id("education", value)
            evidence_id = builder.add_evidence(document_id, evidence_text, "constraints.education")
            builder.add_node(node_id, "Education", {"value": value})
            builder.add_edge(
                job_id,
                "REQUIRES_EDUCATION",
                node_id,
                f"{document_id}:education",
                {"document_id": document_id, "evidence_id": evidence_id, "evidence": evidence_text},
            )
            builder.add_edge(
                node_id,
                "SUPPORTED_BY",
                evidence_id,
                f"{document_id}:education-evidence",
                {"document_id": document_id, "evidence_id": evidence_id},
            )

        if experience.get("value") is not None:
            value = int(experience.get("value"))
            evidence_text = _compact_text(experience.get("evidence"))
            node_id = f"experience_years:{value}"
            evidence_id = builder.add_evidence(document_id, evidence_text, "constraints.experience_years")
            builder.add_node(node_id, "ExperienceRequirement", {"minimum_years": value})
            builder.add_edge(
                job_id,
                "REQUIRES_EXPERIENCE",
                node_id,
                f"{document_id}:experience",
                {"document_id": document_id, "evidence_id": evidence_id, "evidence": evidence_text},
            )
            builder.add_edge(
                node_id,
                "SUPPORTED_BY",
                evidence_id,
                f"{document_id}:experience-evidence",
                {"document_id": document_id, "evidence_id": evidence_id},
            )

        if location.get("value"):
            value = _compact_text(location.get("value"))
            evidence_text = _compact_text(location.get("evidence"))
            node_id = _node_id("location", value)
            evidence_id = builder.add_evidence(document_id, evidence_text, "constraints.location")
            builder.add_node(node_id, "Location", {"value": value})
            builder.add_edge(
                job_id,
                "LOCATED_IN",
                node_id,
                f"{document_id}:location",
                {"document_id": document_id, "evidence_id": evidence_id, "evidence": evidence_text},
            )
            builder.add_edge(
                node_id,
                "SUPPORTED_BY",
                evidence_id,
                f"{document_id}:location-evidence",
                {"document_id": document_id, "evidence_id": evidence_id},
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    nodes = sorted(builder.nodes.values(), key=lambda row: row["node_id"])
    edges = sorted(builder.edges.values(), key=lambda row: row["edge_id"])
    _jsonl_write(output_dir / "graph_nodes.jsonl", nodes)
    _jsonl_write(output_dir / "graph_edges.jsonl", edges)

    validation_report = validate_graph(nodes, edges, raw_text_by_document, profiles)
    summary = _build_summary(profiles, nodes, edges, job_skill_counts, skill_counter, level_counter, validation_report)
    _write_json(output_dir / "graph_summary.json", summary)
    _write_json(output_dir / "validation_report.json", validation_report)
    _write_top_skills(output_dir / "top_skills.csv", skill_counter)
    _write_sample_subgraph(output_dir, profiles, nodes, edges, sample_jobs)
    return summary


def validate_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    raw_text_by_document: dict[str, str],
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    duplicate_node_ids = 0
    duplicate_edge_ids = 0
    invalid_node_labels = 0
    invalid_relation_types = 0
    dangling_edges = 0
    evidence_text_missing = 0

    for node in nodes:
        node_id = node.get("node_id")
        if node_id in node_ids:
            duplicate_node_ids += 1
        node_ids.add(node_id)
        if node.get("label") not in NODE_LABELS:
            invalid_node_labels += 1

    evidence_node_ids = {node["node_id"] for node in nodes if node.get("label") == "Evidence"}
    edge_touches: Counter[str] = Counter()
    skill_edge_count = 0
    skill_edge_with_evidence = 0

    for edge in edges:
        edge_id = edge.get("edge_id")
        if edge_id in edge_ids:
            duplicate_edge_ids += 1
        edge_ids.add(edge_id)
        relation_type = edge.get("relation_type")
        if relation_type not in RELATION_TYPES:
            invalid_relation_types += 1
        source_id = edge.get("source_id")
        target_id = edge.get("target_id")
        if source_id not in node_ids or target_id not in node_ids:
            dangling_edges += 1
        edge_touches[source_id] += 1
        edge_touches[target_id] += 1
        if relation_type in {"REQUIRES_SKILL", "PREFERS_SKILL", "MENTIONS_SKILL"}:
            skill_edge_count += 1
            evidence_id = (edge.get("properties") or {}).get("evidence_id")
            if evidence_id and evidence_id in evidence_node_ids:
                skill_edge_with_evidence += 1

    for node in nodes:
        if node.get("label") != "Evidence":
            continue
        props = node.get("properties") or {}
        document_id = props.get("document_id")
        text = props.get("text") or ""
        raw_text = raw_text_by_document.get(document_id, "")
        if text and _compact_text(text) not in _compact_text(raw_text):
            evidence_text_missing += 1

    job_ids = {f"job:{profile['document_id']}" for profile in profiles}
    jobs_with_skill = {
        edge["source_id"]
        for edge in edges
        if edge.get("relation_type") in {"REQUIRES_SKILL", "PREFERS_SKILL", "MENTIONS_SKILL"}
    }
    jobs_without_skill = len(job_ids - jobs_with_skill)
    isolated_nodes = [node_id for node_id in node_ids if edge_touches[node_id] == 0]

    if duplicate_node_ids:
        errors.append(f"duplicate node ids: {duplicate_node_ids}")
    if duplicate_edge_ids:
        errors.append(f"duplicate edge ids: {duplicate_edge_ids}")
    if invalid_node_labels:
        errors.append(f"invalid node labels: {invalid_node_labels}")
    if invalid_relation_types:
        errors.append(f"invalid relation types: {invalid_relation_types}")
    if dangling_edges:
        errors.append(f"dangling edges: {dangling_edges}")
    if evidence_text_missing:
        errors.append(f"evidence text not found in source raw_text: {evidence_text_missing}")
    if jobs_without_skill:
        warnings.append(f"jobs without skill edges: {jobs_without_skill}")
    if isolated_nodes:
        warnings.append(f"isolated nodes: {len(isolated_nodes)}")

    status = "valid" if not errors else "invalid"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "duplicate_node_ids": duplicate_node_ids,
            "duplicate_edge_ids": duplicate_edge_ids,
            "invalid_node_labels": invalid_node_labels,
            "invalid_relation_types": invalid_relation_types,
            "dangling_edges": dangling_edges,
            "skill_edge_count": skill_edge_count,
            "skill_edges_with_existing_evidence_node": skill_edge_with_evidence,
            "evidence_text_missing_from_raw_text": evidence_text_missing,
            "jobs_without_skill_edges": jobs_without_skill,
            "isolated_node_count": len(isolated_nodes),
        },
    }


def _build_summary(
    profiles: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    job_skill_counts: Counter[str],
    skill_counter: Counter[str],
    level_counter: Counter[str],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    node_counts = Counter(node["label"] for node in nodes)
    edge_counts = Counter(edge["relation_type"] for edge in edges)
    total_jobs = len(profiles)
    jobs_with_skill = sum(1 for profile in profiles if job_skill_counts[profile["document_id"]] > 0)
    jobs_with_education = sum(1 for profile in profiles if ((profile.get("constraints") or {}).get("education") or {}).get("value"))
    jobs_with_experience = sum(1 for profile in profiles if ((profile.get("constraints") or {}).get("experience_years") or {}).get("value") is not None)
    jobs_with_location = sum(1 for profile in profiles if ((profile.get("constraints") or {}).get("location") or {}).get("value"))
    return {
        "schema_version": "jd_kg_v1",
        "source_profile_count": total_jobs,
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "node_counts": dict(node_counts),
        "edge_counts": dict(edge_counts),
        "skill_level_counts": dict(level_counter),
        "coverage": {
            "jobs_with_skill_edges": jobs_with_skill,
            "jobs_with_skill_edges_ratio": round(jobs_with_skill / total_jobs, 4) if total_jobs else 0,
            "jobs_with_education": jobs_with_education,
            "jobs_with_education_ratio": round(jobs_with_education / total_jobs, 4) if total_jobs else 0,
            "jobs_with_experience": jobs_with_experience,
            "jobs_with_experience_ratio": round(jobs_with_experience / total_jobs, 4) if total_jobs else 0,
            "jobs_with_location": jobs_with_location,
            "jobs_with_location_ratio": round(jobs_with_location / total_jobs, 4) if total_jobs else 0,
        },
        "top_skills": [{"name": name, "count": count} for name, count in skill_counter.most_common(30)],
        "validation_status": validation_report["status"],
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_top_skills(path: Path, skill_counter: Counter[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["skill_name", "mention_count"])
        for name, count in skill_counter.most_common():
            writer.writerow([name, count])


def _write_sample_subgraph(
    output_dir: Path,
    profiles: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    sample_jobs: int,
) -> None:
    selected_job_ids = {f"job:{profile['document_id']}" for profile in profiles[:sample_jobs]}
    selected_document_ids = {profile["document_id"] for profile in profiles[:sample_jobs]}
    selected_node_ids = set(selected_job_ids)
    selected_edges: list[dict[str, Any]] = []
    selected_evidence_ids: set[str] = set()
    selected_target_ids: set[str] = set()

    for edge in edges:
        if edge["source_id"] in selected_job_ids:
            selected_edges.append(edge)
            selected_node_ids.add(edge["target_id"])
            selected_target_ids.add(edge["target_id"])
            evidence_id = (edge.get("properties") or {}).get("evidence_id")
            if evidence_id:
                selected_evidence_ids.add(evidence_id)
                selected_node_ids.add(evidence_id)

    for edge in edges:
        props = edge.get("properties") or {}
        if (
            edge["relation_type"] == "SUPPORTED_BY"
            and props.get("document_id") in selected_document_ids
            and edge["source_id"] in selected_target_ids
            and edge["target_id"] in selected_evidence_ids
        ):
            selected_edges.append(edge)
            selected_node_ids.add(edge["source_id"])
            selected_node_ids.add(edge["target_id"])

    selected_nodes = [node for node in nodes if node["node_id"] in selected_node_ids]
    subgraph = {"nodes": selected_nodes, "edges": selected_edges}
    _write_json(output_dir / "sample_subgraph_first_5.json", subgraph)
    _write_sample_markdown(output_dir / "sample_subgraph_first_5.md", profiles[:sample_jobs])
    _write_sample_html(output_dir / "sample_subgraph_first_5.html", selected_nodes, selected_edges)


def _write_sample_markdown(path: Path, profiles: list[dict[str, Any]]) -> None:
    chunks = ["# 前 5 个岗位的图谱构建展示", ""]
    for profile in profiles:
        chunks.append(f"## {profile['document_id']} - {profile.get('title')}")
        chunks.append("")
        chunks.append("| 关系 | 目标节点 | 证据 |")
        chunks.append("| --- | --- | --- |")
        for skill in profile.get("skills") or []:
            relation = SKILL_RELATION_BY_LEVEL.get(skill.get("level"), "MENTIONS_SKILL")
            chunks.append(f"| {relation} | {skill.get('name')} | {skill.get('evidence')} |")
        constraints = profile.get("constraints") or {}
        if (constraints.get("education") or {}).get("value"):
            item = constraints["education"]
            chunks.append(f"| REQUIRES_EDUCATION | {item.get('value')} | {item.get('evidence')} |")
        if (constraints.get("experience_years") or {}).get("value") is not None:
            item = constraints["experience_years"]
            chunks.append(f"| REQUIRES_EXPERIENCE | {item.get('value')}年以上 | {item.get('evidence')} |")
        if (constraints.get("location") or {}).get("value"):
            item = constraints["location"]
            chunks.append(f"| LOCATED_IN | {item.get('value')} | {item.get('evidence')} |")
        chunks.append("")
    path.write_text("\n".join(chunks), encoding="utf-8")


def _write_sample_html(path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    job_nodes = [node for node in nodes if node["label"] == "Job"]
    other_nodes = [node for node in nodes if node["label"] != "Job" and node["label"] != "Evidence"]
    evidence_nodes = [node for node in nodes if node["label"] == "Evidence"]
    ordered_nodes = job_nodes + other_nodes[:25] + evidence_nodes[:18]
    positions: dict[str, tuple[int, int]] = {}
    columns = {"Job": 90, "Skill": 370, "Education": 370, "ExperienceRequirement": 370, "Location": 370, "Evidence": 700}
    offsets: defaultdict[str, int] = defaultdict(int)
    for node in ordered_nodes:
        label = node["label"]
        y = 60 + offsets[label] * 58
        positions[node["node_id"]] = (columns.get(label, 500), y)
        offsets[label] += 1

    width = 980
    height = max(420, max((y for _, y in positions.values()), default=360) + 80)
    lines = []
    for edge in edges:
        if edge["source_id"] not in positions or edge["target_id"] not in positions:
            continue
        x1, y1 = positions[edge["source_id"]]
        x2, y2 = positions[edge["target_id"]]
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9aa6b2" stroke-width="1.2" />')

    node_svg = []
    color_by_label = {
        "Job": "#2563eb",
        "Skill": "#059669",
        "Education": "#7c3aed",
        "ExperienceRequirement": "#ea580c",
        "Location": "#0891b2",
        "Evidence": "#64748b",
    }
    for node in ordered_nodes:
        x, y = positions[node["node_id"]]
        props = node.get("properties") or {}
        label = props.get("title") or props.get("name") or props.get("value") or props.get("text") or node["node_id"]
        label = html.escape(str(label)[:34])
        fill = color_by_label.get(node["label"], "#475569")
        node_svg.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{fill}" />')
        node_svg.append(f'<text x="{x + 20}" y="{y + 5}" font-size="12" fill="#111827">{label}</text>')

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>JD KG Sample Subgraph</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #111827; }}
.caption {{ color: #4b5563; margin-bottom: 12px; }}
svg {{ border: 1px solid #d1d5db; background: #f8fafc; max-width: 100%; }}
</style>
<h1>9000 JD 知识图谱局部展示</h1>
<p class="caption">展示前 5 个 Job 节点连接到 Skill / Education / Experience / Location / Evidence 的局部子图。</p>
<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">
<text x="90" y="28" font-size="15" font-weight="700">Job</text>
<text x="370" y="28" font-size="15" font-weight="700">Ability / Constraint</text>
<text x="700" y="28" font-size="15" font-weight="700">Evidence</text>
{''.join(lines)}
{''.join(node_svg)}
</svg>
</html>
"""
    path.write_text(html_text, encoding="utf-8")
