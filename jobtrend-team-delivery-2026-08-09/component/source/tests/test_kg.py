from __future__ import annotations

import json
from pathlib import Path

import pytest

from trend_discovery.io_utils import sha256_file
from trend_discovery.kg import KGIndex, import_kg_bundle


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def jd_kg_bundle(root: Path) -> tuple[Path, Path, Path]:
    nodes = root / "graph_nodes.jsonl"
    edges = root / "graph_edges.jsonl"
    profiles = root / "profiles.jsonl"
    write_jsonl(
        nodes,
        [
            {"node_id": "job:original-1", "label": "Job", "properties": {"title": "Java开发工程师"}},
            {"node_id": "skill:python-original", "label": "Skill", "properties": {"name": "Python"}},
            {
                "node_id": "evidence:original-1",
                "label": "Evidence",
                "properties": {"text": "熟练使用 Python"},
            },
        ],
    )
    write_jsonl(
        edges,
        [
            {
                "edge_id": "edge:1",
                "source_id": "job:original-1",
                "target_id": "skill:python-original",
                "relation_type": "REQUIRES_SKILL",
                "properties": {},
            },
            {
                "edge_id": "edge:2",
                "source_id": "skill:python-original",
                "target_id": "evidence:original-1",
                "relation_type": "SUPPORTED_BY",
                "properties": {},
            },
        ],
    )
    write_jsonl(profiles, [{"schema_version": "jd_profile_v1", "document_id": "JD1"}])
    return nodes, edges, profiles


def test_import_preserves_ids_fingerprints_and_supports_two_hops(tmp_path: Path) -> None:
    nodes, edges, profiles = jd_kg_bundle(tmp_path)
    source_hashes = (sha256_file(nodes), sha256_file(edges), sha256_file(profiles))
    output = tmp_path / "index"

    summary = import_kg_bundle(nodes, edges, profiles, output)
    index = KGIndex.load(output, curated_aliases={"Py": "skill:python-original"})

    assert summary["source_schema"] == "jd_kg_v1"
    assert summary["counts"] == {"nodes": 3, "edges": 2, "jobs": 1, "abilities": 1}
    assert (sha256_file(nodes), sha256_file(edges), sha256_file(profiles)) == source_hashes
    assert index.resolve_ability("PYTHON").source_node_id == "skill:python-original"
    assert index.resolve_ability("Py").resolution_status == "curated_alias"
    semantic = index.resolve_ability("Pythn", semantic_threshold=0.60)
    assert semantic.resolution_status == "review_candidate"
    assert semantic.source_node_id == "skill:python-original"
    assert index.resolve_ability("完全无关能力", semantic_threshold=0.95).resolution_status == "unresolved"
    neighborhood = index.neighbors("job:original-1", hops=2)
    assert {row["node_id"] for row in neighborhood["nodes"]} == {
        "job:original-1",
        "skill:python-original",
        "evidence:original-1",
    }
    assert index.search_jobs("Java开发工程师", 1)[0]["node_id"] == "job:original-1"
    assert index.job_ability_names("job:original-1") == ("Python",)


def test_small_raw_v2_category_and_dangling_edge_validation(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.jsonl"
    edges = tmp_path / "edges.jsonl"
    profiles = tmp_path / "jd_profiles.jsonl"
    write_jsonl(
        nodes,
        [
            {"node_id": "job:42", "label": "Job", "properties": {"title": "算法工程师"}},
            {
                "node_id": "tech:python-kept",
                "label": "Skill",
                "properties": {"category": "Tech", "name": "Python"},
            },
        ],
    )
    write_jsonl(
        edges,
        [
            {
                "edge_id": "edge:kept",
                "source_id": "job:42",
                "target_id": "tech:python-kept",
                "relation_type": "REQUIRES_TECHNOLOGY",
            }
        ],
    )
    write_jsonl(
        profiles,
        [{"schema_version": "small-raw-lskt-tech/v2", "record_type": "jd", "record_id": "42"}],
    )
    summary = import_kg_bundle(nodes, edges, profiles, tmp_path / "output")
    index = KGIndex.load(tmp_path / "output")
    assert summary["source_schema"] == "small-raw-lskt-tech/v2"
    assert index.resolve_ability("python").category == "Tech"
    assert index.resolve_ability("python").source_node_id == "tech:python-kept"

    write_jsonl(
        edges,
        [
            {
                "edge_id": "broken",
                "source_id": "job:42",
                "target_id": "missing",
                "relation_type": "REQUIRES_SKILL",
            }
        ],
    )
    with pytest.raises(ValueError, match="dangling"):
        import_kg_bundle(nodes, edges, profiles)
