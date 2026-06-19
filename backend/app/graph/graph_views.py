"""Graph view extraction for the unified graph schema."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence, Set

from backend.app.graph.graph_schema import make_graph


VIEW_FILES = {
    "position": "graph_position_view.json",
    "tech_stack": "graph_tech_stack_view.json",
    "level": "graph_level_view.json",
    "match": "graph_match_view.json",
    "evolution": "graph_evolution_view.json",
}


def build_graph_views(graph: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {view_type: get_graph_view(graph, view_type) for view_type in VIEW_FILES}


def get_graph_view(graph: Mapping[str, Any], view_type: str) -> Dict[str, Any]:
    if view_type == "position":
        return _filter_graph(graph, "graph_position_view", {"Position", "Capability", "Skill"}, {"requires_capability", "contains_skill", "requires_skill"})
    if view_type == "tech_stack":
        return _filter_graph(graph, "graph_tech_stack_view", {"TechStack", "Skill", "Position"}, {"contains_skill", "belongs_to_stack", "requires_skill"})
    if view_type == "level":
        return _filter_graph(graph, "graph_level_view", {"Position", "Candidate", "Skill", "Level"}, {"requires_skill", "has_skill", "partially_matches", "lacks", "contains_skill"})
    if view_type == "match":
        view = _filter_graph(graph, "graph_match_view", {"Position", "Candidate", "Skill"}, {"matches", "requires_skill", "has_skill", "lacks", "partially_matches"})
        view["metadata"].update(_match_view_metadata(view))
        return view
    if view_type == "evolution":
        return _filter_graph(graph, "graph_evolution_view", {"Position", "Skill", "Version"}, {"newly_requires", "rising_in", "declining_in"})
    raise ValueError(f"unsupported graph view type: {view_type}")


def _filter_graph(graph: Mapping[str, Any], graph_id: str, node_types: Set[str], relations: Set[str]) -> Dict[str, Any]:
    original_nodes = {node["id"]: dict(node) for node in graph.get("nodes", []) if node.get("type") in node_types}
    edges = [
        dict(edge)
        for edge in graph.get("edges", [])
        if edge.get("relation") in relations and edge.get("source") in original_nodes and edge.get("target") in original_nodes
    ]
    used_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    nodes = [node for node_id, node in original_nodes.items() if node_id in used_ids or node.get("type") in {"Position", "Candidate", "Version"}]
    metadata = dict(graph.get("metadata") or {})
    metadata.update({"view_type": graph_id.replace("graph_", "").replace("_view", ""), "source_graph_id": graph.get("graph_id")})
    return make_graph(graph_id, nodes, edges, metadata, version=str(graph.get("version", "demo-v1")))


def _match_view_metadata(graph: Mapping[str, Any]) -> Dict[str, Any]:
    node_by_id = {node["id"]: node for node in graph.get("nodes", [])}
    matched = []
    missing = []
    partial = []
    for edge in graph.get("edges", []):
        target_node = node_by_id.get(edge.get("target"))
        if not target_node or target_node.get("type") != "Skill":
            continue
        item = {
            "skill_id": target_node["id"],
            "name": target_node["label"],
            "weight": edge.get("weight"),
            "properties": edge.get("properties", {}),
        }
        if edge.get("relation") == "has_skill":
            matched.append(item)
        elif edge.get("relation") == "lacks":
            missing.append(item)
        elif edge.get("relation") == "partially_matches":
            partial.append(item)
    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "partial_skills": partial,
    }
