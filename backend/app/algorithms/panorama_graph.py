"""Build panorama job-skill graphs from multiple JD texts.

This module is intentionally separate from person-job matching. It supports the
competition requirement for a new-generation IT job panorama graph, while the
matching graph remains a local graph for one JD and one resume.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.app.algorithms.pipeline import parse_jd
from backend.app.algorithms.skill_catalog import RELATED_LOOKUP, SKILL_CATALOG, skill_id_for


def build_panorama_graph(job_documents: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a multi-job ability graph.

    Input documents are lightweight dictionaries:
    {
      "id": "jd_x",
      "text": "...",
      "level": "中级",
      "source_type": "sample_jd"
    }
    """
    documents = [document for index, item in enumerate(job_documents) if (document := _normalize_job_document(item, index))]
    if not documents:
        raise ValueError("job_documents must contain at least one non-empty text")

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    skill_support: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"jobs": set(), "weight_sum": 0.0, "max_weight": 0.0})
    category_counter: Counter[str] = Counter()
    level_counter: Counter[str] = Counter()

    def add_node(node_id: str, node_type: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        existing = nodes.get(node_id)
        if existing:
            existing["properties"].update(properties or {})
            return
        nodes[node_id] = {"id": node_id, "type": node_type, "label": label, "level": 0, "properties": properties or {}}

    def add_edge(source: str, target: str, edge_type: str, weight: float, properties: Optional[Dict[str, Any]] = None) -> None:
        key = (source, target, edge_type)
        if key in edges:
            edges[key]["weight"] = round(max(float(edges[key]["weight"]), float(weight)), 3)
            edges[key]["properties"].update(properties or {})
            return
        edges[key] = {
            "source": source,
            "target": target,
            "type": edge_type,
            "relation": edge_type,
            "weight": round(float(weight), 3),
            "properties": properties or {},
        }

    add_node("domain:new_it", "Domain", "新一代信息技术", {"description": "人工智能、大数据、智能系统、物联网等数字经济岗位"})

    for document in documents:
        parsed = parse_jd(document["text"])
        jd_parse = parsed["jd_parse"]
        job_profile = parsed["job_profile"]
        job_id = f"job:{document['id']}"
        category = jd_parse.get("job_category") or "通用技术岗"
        level = document.get("level") or infer_level(job_profile.get("metadata", {}), job_profile.get("skills", []))
        category_id = f"job_category:{category}"
        level_id = f"level:{level}"
        category_counter[category] += 1
        level_counter[level] += 1

        add_node(
            job_id,
            "Job",
            jd_parse.get("job_title") or document["id"],
            {
                "job_category": category,
                "level": level,
                "source_id": document["id"],
                "source_type": document.get("source_type", "jd"),
            },
        )
        add_node(category_id, "JobCategory", category, {})
        add_node(level_id, "Level", level, {})
        add_edge("domain:new_it", job_id, "contains_job", 1.0, {})
        add_edge(job_id, category_id, "belongs_to_category", 1.0, {})
        add_edge(job_id, level_id, "has_level", 1.0, {})

        for skill in job_profile.get("skills", []):
            skill_name = skill["name"]
            skill_id = skill["skill_id"]
            skill_type = skill["skill_type"]
            skill_type_id = f"skill_type:{skill_type}"
            weight = float(skill.get("weight", 0.0))

            add_node(
                skill_id,
                "Skill",
                skill_name,
                {
                    "skill_type": skill_type,
                    "support_count": 0,
                    "max_weight": 0.0,
                },
            )
            add_node(skill_type_id, "SkillType", skill_type, {})
            add_edge(skill_id, skill_type_id, "belongs_to_skill_type", 1.0, {})
            add_edge(job_id, skill_id, "requires", weight, {"requirement_level": skill.get("requirement_level")})

            support = skill_support[skill_name]
            support["jobs"].add(job_id)
            support["weight_sum"] += weight
            support["max_weight"] = max(float(support["max_weight"]), weight)

    skill_names = set(skill_support)
    for skill_name, support in skill_support.items():
        skill_id = SKILL_CATALOG.get(skill_name, {}).get("skill_id", skill_id_for(skill_name))
        support_count = len(support["jobs"])
        nodes[skill_id]["properties"]["support_count"] = support_count
        nodes[skill_id]["properties"]["max_weight"] = round(float(support["max_weight"]), 3)
        nodes[skill_id]["properties"]["avg_weight"] = round(float(support["weight_sum"]) / max(1, support_count), 3)

    for source, related_items in RELATED_LOOKUP.items():
        if source not in skill_names:
            continue
        source_id = SKILL_CATALOG[source]["skill_id"]
        for target, relation_type in related_items:
            if target in skill_names:
                add_edge(source_id, SKILL_CATALOG[target]["skill_id"], "related_to", 0.5, {"relation_type": relation_type})

    views = build_graph_views(nodes, edges)
    metadata = {
        "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "schema_version": "panorama-demo-v1",
        "job_count": len(documents),
        "skill_count": len([node for node in nodes.values() if node["type"] == "Skill"]),
        "category_distribution": dict(category_counter),
        "level_distribution": dict(level_counter),
        "competition_hooks": {
            "supports_panorama_graph": True,
            "supports_stack_view": True,
            "supports_level_view": True,
            "next_stage_required": ["interactive_frontend", "time_series_graph", "manual_optimization"],
        },
    }
    graph = {
        "mode": "job_skill_panorama_graph",
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "views": views,
        "graph_metadata": metadata,
        "metadata": metadata,
    }
    return graph


def build_graph_views(nodes: Mapping[str, Dict[str, Any]], edges: Mapping[Tuple[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    stack_view: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    level_view: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    job_nodes = {node_id: node for node_id, node in nodes.items() if node["type"] == "Job"}
    skill_nodes = {node_id: node for node_id, node in nodes.items() if node["type"] == "Skill"}

    for edge in edges.values():
        if edge["type"] != "requires":
            continue
        job = job_nodes.get(edge["source"])
        skill = skill_nodes.get(edge["target"])
        if not job or not skill:
            continue
        item = {
            "job_id": job["id"],
            "job_title": job["label"],
            "skill_id": skill["id"],
            "skill_name": skill["label"],
            "weight": edge["weight"],
            "requirement_level": edge["properties"].get("requirement_level"),
        }
        stack_view[skill["properties"].get("skill_type", "未知")].append(item)
        level_view[job["properties"].get("level", "未标注")].append(item)

    for items in stack_view.values():
        items.sort(key=lambda item: (-item["weight"], item["job_title"], item["skill_name"]))
    for items in level_view.values():
        items.sort(key=lambda item: (-item["weight"], item["job_title"], item["skill_name"]))
    return {"by_skill_type": dict(stack_view), "by_level": dict(level_view)}


def infer_level(metadata: Mapping[str, Any], skills: Sequence[Mapping[str, Any]]) -> str:
    required_years = metadata.get("experience_requirement")
    if required_years is not None:
        if float(required_years) >= 5:
            return "高级"
        if float(required_years) >= 2:
            return "中级"
        return "初级"
    strong_skills = [skill for skill in skills if float(skill.get("weight", 0.0)) >= 1.2]
    if len(strong_skills) >= 6:
        return "高级"
    if len(strong_skills) >= 3:
        return "中级"
    return "未标注"


def _normalize_job_document(item: Mapping[str, Any], index: int) -> Dict[str, Any]:
    text = str(item.get("text", "")).strip()
    if not text:
        return {}
    return {
        "id": item.get("id") or item.get("source_id") or f"job_doc_{index + 1:03d}",
        "text": text,
        "level": normalize_level(item.get("level") or item.get("seniority")),
        "source_type": item.get("source_type", "jd"),
    }


def normalize_level(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if any(token in text for token in ("高级", "专家", "资深", "5年以上", "6年", "7年", "8年", "9年", "10年")):
        return "高级"
    if any(token in text for token in ("中级", "2年", "3年", "4年", "3-5", "2-5", "3-6")):
        return "中级"
    if any(token in text for token in ("初级", "应届", "实习", "1年")):
        return "初级"
    return text or None
