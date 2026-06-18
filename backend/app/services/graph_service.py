"""Graph service for saved full graph, graph views, and panorama graph."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from backend.app.algorithms.panorama_graph import build_panorama_graph
from backend.app.graph.graph_repository import load_graph_full, load_graph_view


def get_full_graph() -> Dict[str, Any]:
    graph = load_graph_full(default=None)
    if graph is None:
        return {"graph_id": "graph_full", "version": "", "generated_at": "", "nodes": [], "edges": [], "metadata": {"status": "not_generated"}}
    return graph


def get_graph_view(view_type: str) -> Dict[str, Any]:
    graph = load_graph_view(view_type, default=None)
    if graph is None:
        return {"graph_id": f"graph_{view_type}_view", "version": "", "generated_at": "", "nodes": [], "edges": [], "metadata": {"status": "not_generated", "view_type": view_type}}
    graph = dict(graph)
    graph.setdefault("metadata", {})["view_type"] = view_type
    return graph


def build_panorama(job_documents: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return build_panorama_graph(job_documents)
