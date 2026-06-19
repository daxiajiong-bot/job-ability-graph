"""Unified graph schema helpers for demo graph artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.app.core.config import DEFAULT_GRAPH_VERSION


NODE_TYPES = {
    "Position",
    "Capability",
    "TechStack",
    "Skill",
    "Level",
    "Candidate",
    "Evidence",
    "Version",
}

RELATIONS = {
    "requires_skill",
    "requires_capability",
    "contains_skill",
    "belongs_to_stack",
    "has_skill",
    "supports",
    "matches",
    "lacks",
    "partially_matches",
    "newly_requires",
    "rising_in",
    "declining_in",
}


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_node(
    node_id: str,
    label: str,
    node_type: str,
    level: int = 0,
    properties: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(node_id),
        "label": str(label),
        "type": str(node_type),
        "level": int(level),
        "properties": dict(properties or {}),
    }


def make_edge(
    source: str,
    target: str,
    relation: str,
    weight: float = 1.0,
    properties: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "source": str(source),
        "target": str(target),
        "relation": str(relation),
        "weight": round(float(weight), 3),
        "properties": dict(properties or {}),
    }


def make_graph(
    graph_id: str,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    metadata: Optional[Mapping[str, Any]] = None,
    version: str = DEFAULT_GRAPH_VERSION,
) -> Dict[str, Any]:
    node_list: List[Dict[str, Any]] = [dict(node) for node in nodes]
    edge_list: List[Dict[str, Any]] = [dict(edge) for edge in edges]
    return {
        "graph_id": graph_id,
        "version": version,
        "generated_at": generated_at(),
        "nodes": node_list,
        "edges": edge_list,
        "metadata": dict(metadata or {}),
    }
