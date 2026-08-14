"""Merge JobTrend ``kg_link_delta.jsonl`` into Neo4j (graph self-evolution).

The trend component only *proposes* graph changes (append-only). This script
applies them to Neo4j as a new evolution snapshot, so the reviewer-approved
deltas become queryable graph structure:

  EmergingRole ──REQUIRES_SKILL/PREFERS_SKILL──> Ability

Usage (from repo root, with the backend venv):

    # default: only apply reviewer-approved deltas (resolution_status=approved)
    python scripts/merge_kg_delta.py

    # demo: also apply unresolved deltas (the shipped demo data is unresolved)
    python scripts/merge_kg_delta.py --force

    # point at another delta file / snapshot id
    python scripts/merge_kg_delta.py --delta path/to/kg_link_delta.jsonl --snapshot kg_evolved_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.infrastructure.neo4j.adapters import Neo4jGraphStore, Neo4jSettings  # noqa: E402

DEFAULT_DELTA = (
    REPO_ROOT
    / "jobtrend-team-delivery-2026-08-09"
    / "component"
    / "kg_link_delta.jsonl"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delta", type=str, default=str(DEFAULT_DELTA))
    parser.add_argument("--snapshot", type=str, default="kg_evolved_v1")
    parser.add_argument("--force", action="store_true", help="apply unresolved deltas too (demo)")
    args = parser.parse_args()

    delta_path = Path(args.delta)
    if not delta_path.exists():
        print(f"delta file not found: {delta_path}")
        sys.exit(1)

    deltas = []
    for line in delta_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            deltas.append(json.loads(line))

    applyable = [
        d for d in deltas
        if d.get("operation", "").startswith("propose_")
        and (args.force or d.get("resolution_status") == "approved")
    ]
    skipped = len(deltas) - len(applyable)
    print(f"delta total={len(deltas)} applyable={len(applyable)} skipped={skipped} (--force={args.force})", flush=True)

    # Pass 1: node registry from propose_node deltas (file order is arbitrary,
    # edges may appear before their node proposals).
    node_registry: dict[str, dict] = {}  # node_id -> {"label", "properties"}
    for delta in applyable:
        if delta["operation"] != "propose_node" or not delta.get("source_id"):
            continue
        source_id = delta["source_id"]
        props = dict(delta.get("properties") or {})
        label = props.pop("label", None) or _label_from_id(source_id)
        name = (
            props.pop("canonical_title", None)
            or props.pop("canonical_name", None)
            or props.pop("ability_name", None)
            or props.pop("name", None)
            or source_id
        )
        node_registry[source_id] = {
            "label": label,
            "properties": {"name": name, **props},
        }

    # Pass 2: edges, ensuring endpoint nodes exist.
    nodes_by_label: dict[str, list[dict]] = {}
    relationships_by_group: dict[tuple[str, str, str], list[dict]] = {}

    def ensure_node(node_id: str) -> str:
        entry = node_registry.get(node_id)
        if entry is None:
            label = _label_from_id(node_id)
            entry = {"label": label, "properties": {"name": node_id}}
            node_registry[node_id] = entry
        rows = nodes_by_label.setdefault(entry["label"], [])
        if not any(r["id"] == node_id for r in rows):
            rows.append({"id": node_id, "properties": dict(entry["properties"])})
        return entry["label"]

    for delta in applyable:
        if delta["operation"] != "propose_edge":
            continue
        source_id = delta.get("source_id")
        target_id = delta.get("target_id")
        if not source_id or not target_id:
            continue
        source_label = ensure_node(source_id)
        target_label = ensure_node(target_id)
        edge_props = {"evidence_ids": delta.get("evidence_ids") or []}
        if delta.get("resolution_status"):
            edge_props["resolution_status"] = delta["resolution_status"]
        group = (source_label, delta["relation_type"], target_label)
        relationships_by_group.setdefault(group, []).append(
            {"start_id": source_id, "end_id": target_id, "properties": edge_props}
        )

    payload = {
        "snapshot": {
            "id": args.snapshot,
            "properties": {"name": "JobTrend kg_link_delta evolution", "source": str(delta_path)},
        },
        "nodes_by_label": nodes_by_label,
        "relationships_by_group": relationships_by_group,
    }
    node_count = sum(len(v) for v in nodes_by_label.values())
    edge_count = sum(len(v) for v in relationships_by_group.values())
    print(f"evolution snapshot {args.snapshot}: nodes={node_count} edges={edge_count}", flush=True)
    if node_count == 0 and edge_count == 0:
        print("nothing to merge; try --force to include unresolved demo deltas", flush=True)
        return

    store = Neo4jGraphStore(Neo4jSettings.from_env())
    try:
        store.write_graph(payload)
        print(f"merged into Neo4j as snapshot {args.snapshot}", flush=True)
    finally:
        store.close()


def _label_from_id(node_id: str) -> str:
    """Map id prefixes like ``role:...`` / ``ability:...`` to Neo4j labels."""
    prefix = node_id.split(":", 1)[0]
    return {
        "role": "EmergingRole",
        "ability": "Ability",
        "skill": "Skill",
        "job": "Job",
        "tech": "Technology",
        "evidence": "Evidence",
    }.get(prefix, prefix.capitalize())


if __name__ == "__main__":
    main()
