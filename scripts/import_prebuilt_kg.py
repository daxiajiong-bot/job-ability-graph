"""Import the pre-built knowledge graph (small_raw_200_lskt_tech_v2) into Neo4j.

Reads ``data/small_raw_200_lskt_tech_v2/graph_nodes.jsonl`` and
``graph_edges.jsonl`` and writes them as one snapshot via the project's
``Neo4jGraphStore`` so the API graph-retrieval path can query it.

Usage (from repo root, with the backend venv):

    python scripts/import_prebuilt_kg.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.infrastructure.neo4j.adapters import (  # noqa: E402
    Neo4jGraphStore,
    Neo4jSettings,
)

SNAPSHOT_ID = "kg_prebuilt_v2"
GRAPH_DIR = REPO_ROOT / "data" / "small_raw_200_lskt_tech_v2"


def main() -> None:
    nodes_file = GRAPH_DIR / "graph_nodes.jsonl"
    edges_file = GRAPH_DIR / "graph_edges.jsonl"
    if not nodes_file.exists() or not edges_file.exists():
        print(f"graph files not found in {GRAPH_DIR}")
        sys.exit(1)

    # ── Load nodes ──
    node_by_id: dict[str, dict] = {}
    nodes_by_label: dict[str, list[dict]] = {}
    for line in nodes_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        node = json.loads(line)
        label = node.get("label", "")
        node_id = node.get("node_id", "")
        if not label or not node_id:
            continue
        props = dict(node.get("properties") or {})
        # Ensure a name-like property so the retriever's CONTAINS matching works.
        if not any(props.get(k) for k in ("name", "title")):
            props["name"] = node_id
        node_by_id[node_id] = {"label": label, "id": node_id, "properties": props}
        nodes_by_label.setdefault(label, []).append({"id": node_id, "properties": props})

    # ── Load edges, grouped by (start_label, rel_type, end_label) ──
    relationships_by_group: dict[tuple[str, str, str], list[dict]] = {}
    missing = 0
    for line in edges_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        edge = json.loads(line)
        start_id = edge.get("source_id", "")
        end_id = edge.get("target_id", "")
        rel_type = edge.get("relation_type", "")
        if start_id not in node_by_id or end_id not in node_by_id:
            missing += 1
            continue
        start_label = node_by_id[start_id]["label"]
        end_label = node_by_id[end_id]["label"]
        props = dict(edge.get("properties") or {})
        if edge.get("evidence_ids"):
            props["evidence_ids"] = edge["evidence_ids"]
        group = (start_label, rel_type, end_label)
        relationships_by_group.setdefault(group, []).append(
            {"start_id": start_id, "end_id": end_id, "properties": props}
        )

    payload = {
        "snapshot": {
            "id": SNAPSHOT_ID,
            "properties": {
                "name": "prebuilt small_raw_200_lskt_tech_v2",
                "source": str(GRAPH_DIR),
            },
        },
        "nodes_by_label": nodes_by_label,
        "relationships_by_group": relationships_by_group,
    }

    print(
        f"nodes={sum(len(v) for v in nodes_by_label.values())} "
        f"edges={sum(len(v) for v in relationships_by_group.values())} "
        f"missing_edges={missing}",
        flush=True,
    )

    store = Neo4jGraphStore(Neo4jSettings.from_env())
    try:
        store.write_graph(payload)
        print(f"imported snapshot {SNAPSHOT_ID} into Neo4j", flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
