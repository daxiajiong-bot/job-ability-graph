"""Persist and load full graph artifacts and view artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from backend.app.graph.graph_views import VIEW_FILES, build_graph_views
from backend.app.storage import paths
from backend.app.storage.json_store import load_json, save_json


FULL_GRAPH_FILE = "graph_full.json"


def save_graph_bundle(graph: Mapping[str, Any], views: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Dict[str, str]:
    graph_copy = dict(graph)
    graph_copy["metadata"] = dict(graph_copy.get("metadata") or {})
    planned_paths = {"full": str(paths.GRAPH_DIR / FULL_GRAPH_FILE)}
    planned_paths.update({view_type: str(paths.GRAPH_DIR / filename) for view_type, filename in VIEW_FILES.items()})
    graph_copy["metadata"]["graph_paths"] = planned_paths
    graph_views = dict(views or build_graph_views(graph_copy))
    saved = {"full": str(save_json(paths.GRAPH_DIR / FULL_GRAPH_FILE, graph_copy))}
    for view_type, filename in VIEW_FILES.items():
        if view_type in graph_views:
            saved[view_type] = str(save_json(paths.GRAPH_DIR / filename, dict(graph_views[view_type])))
    return saved


def load_graph_full(default: Any = None) -> Any:
    return load_json(paths.GRAPH_DIR / FULL_GRAPH_FILE, default=default)


def load_graph_view(view_type: str, default: Any = None) -> Any:
    filename = VIEW_FILES.get(view_type)
    if not filename:
        raise ValueError(f"unsupported graph view type: {view_type}")
    return load_json(paths.GRAPH_DIR / filename, default=default)
