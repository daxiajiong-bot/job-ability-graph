from pathlib import Path
from types import SimpleNamespace

import pytest

from trend_discovery.ingest import ingest_manifest
from trend_discovery.io_utils import read_jsonl
from trend_discovery.pipeline import _validate_kg_references, analyze_warehouse, mark_latest_success
from trend_discovery.settings import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_sample_pipeline_emits_auditable_contract(tmp_path: Path) -> None:
    config = load_config(PROJECT_ROOT / "config" / "default.yaml")
    config["paths"]["qdrant"] = str(tmp_path / "qdrant")
    warehouse = tmp_path / "warehouse"
    output = tmp_path / "output"
    ingest = ingest_manifest(PROJECT_ROOT / "data" / "samples" / "sources.yaml", warehouse, config)
    assert ingest["documents_parsed"] == 122

    result = analyze_warehouse(config=config, warehouse_dir=warehouse, output_dir=output)
    assert result["counts"]["observations"] == 120
    assert result["counts"]["emerging_roles"] >= 1
    assert result["counts"]["job_skill_updates"] >= 1
    assert result["quality"] == "valid"

    roles = list(read_jsonl(output / "emerging_roles.jsonl"))
    assert any("智能体" in role["canonical_title"] or "Agent" in role["canonical_title"] for role in roles)
    assert all(role["canonical_title"] != "Java开发工程师" for role in roles)
    updates = list(read_jsonl(output / "job_skill_updates.jsonl"))
    java = next(item for item in updates if item["canonical_role"] == "Java开发工程师")
    assert {item["skill_name"] for item in java["changes"]} >= {"RAG", "MCP", "大模型API"}
    assert (output / "review_queue.csv").is_file()
    assert (output / "rag_contexts.jsonl").is_file()

    state = mark_latest_success(tmp_path / "runs", result)
    assert state.is_file()


def test_kg_reference_gate_allows_same_delta_proposals_but_rejects_dangling() -> None:
    kg = SimpleNamespace(nodes={"skill:existing": {}})
    proposed = SimpleNamespace(operation="propose_node", source_id="ability:new", target_id=None)
    proposed_edge = SimpleNamespace(
        operation="propose_edge", source_id="role:new", target_id="ability:new"
    )
    existing_edge = SimpleNamespace(
        operation="link_existing", source_id="role:new", target_id="skill:existing"
    )
    result = _validate_kg_references([], [], [proposed, proposed_edge, existing_edge], kg)
    assert result["status"] == "valid"
    assert result["proposed_ids"] == 1

    dangling = SimpleNamespace(operation="propose_edge", source_id="role:new", target_id="missing")
    with pytest.raises(ValueError, match="dangling node IDs"):
        _validate_kg_references([], [], [dangling], kg)
