from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .analysis import analyze_trends, build_job_observations
from .cloud_models import DashScopeEmbeddingClient, DashScopeRerankClient
from .io_utils import read_jsonl, sha256_file, stable_id, write_json, write_jsonl
from .kg import KGIndex, import_kg_bundle
from .provenance import artifact_info, new_run_manifest
from .quality import validate_output_directory
from .retrieval import HybridEvidenceIndex
from .review import export_review_queue
from .schemas import EmergingRole, Evidence, RunManifest
from .warehouse import Warehouse


PUBLIC_ANALYSIS_FILES = (
    "external_documents.jsonl",
    "evidence.jsonl",
    "trend_features.jsonl",
    "emerging_roles.jsonl",
    "job_skill_updates.jsonl",
    "review_queue.csv",
    "kg_link_delta.jsonl",
)


def import_graph(
    *,
    nodes: str | Path,
    edges: str | Path,
    profiles: str | Path | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    return import_kg_bundle(nodes, edges, profiles, output_dir)


def analyze_warehouse(
    *,
    config: Mapping[str, Any],
    warehouse_dir: str | Path,
    output_dir: str | Path,
    kg_index_dir: str | Path | None = None,
    as_of: datetime | None = None,
    use_cloud_retrieval: bool = False,
) -> dict[str, Any]:
    """Run deterministic gates, persist RAG contexts and emit the public contract."""

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    warehouse = Warehouse(warehouse_dir)
    documents = warehouse.load_documents()
    evidence = warehouse.load_evidence()
    if not documents:
        raise ValueError("warehouse has no documents; run jobtrend ingest first")
    observations = build_job_observations(documents, evidence, config)
    if len(observations) < 1:
        raise ValueError("warehouse has no parsed job observations")

    kg_index = KGIndex.load(kg_index_dir) if kg_index_dir else None
    features, emerging, updates, deltas, analysis_summary = analyze_trends(
        observations, evidence, kg_index, config, as_of
    )
    kg_reference_gate = _validate_kg_references(emerging, updates, deltas, kg_index)

    retrieval_config = dict(config.get("retrieval") or {})
    models = dict(config.get("models") or {})
    dimension = int(models.get("embedding_dimension", 1024))
    embedder = None
    reranker = None
    retrieval_provider = "offline-feature-hash"
    if use_cloud_retrieval:
        embedder = DashScopeEmbeddingClient(
            model=str(models.get("embedding_model", "text-embedding-v4")),
            dimension=dimension,
            base_url=str(models.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        )
        reranker = DashScopeRerankClient(model=str(models.get("rerank_model", "qwen3-rerank")))
        retrieval_provider = "dashscope"
    index = HybridEvidenceIndex.build(
        evidence,
        qdrant_path=str(config.get("paths", {}).get("qdrant")) if evidence else None,
        embedding_dimension=dimension,
        embedder=embedder,
    )
    try:
        contexts = _build_rag_contexts(
            emerging,
            evidence,
            index,
            kg_index,
            retrieval_config,
            reranker=reranker,
        )
    finally:
        index.close()

    warehouse.export(output)
    write_jsonl(output / "job_observations.jsonl", observations)
    write_jsonl(output / "trend_features.jsonl", features)
    write_jsonl(output / "emerging_roles.jsonl", emerging)
    write_jsonl(output / "job_skill_updates.jsonl", updates)
    write_jsonl(output / "kg_link_delta.jsonl", deltas)
    write_jsonl(output / "rag_contexts.jsonl", contexts)
    export_review_queue(
        output / "review_queue.csv",
        emerging_roles_path=output / "emerging_roles.jsonl",
        job_skill_updates_path=output / "job_skill_updates.jsonl",
        kg_link_delta_path=output / "kg_link_delta.jsonl",
    )
    quality = validate_output_directory(output)
    quality["kg_reference_gate"] = kg_reference_gate
    write_json(output / "quality_report.json", quality)
    if quality["status"] != "valid":
        raise ValueError(f"evidence quality gate failed: {quality}")

    manifest = new_run_manifest(
        config_sha256=str(config.get("_sha256") or "unknown"),
        model_ids={
            "extraction": str(models.get("extraction_model", "")),
            "fallback": str(models.get("fallback_model", "")),
            "embedding": str(models.get("embedding_model", "")),
            "rerank": str(models.get("rerank_model", "")),
        },
        baseline_graph_fingerprint=kg_index.fingerprint if kg_index else None,
        notes={
            "retrieval_provider": retrieval_provider,
            "cloud_calls_executed": bool(use_cloud_retrieval),
            "analysis": analysis_summary,
        },
    )
    manifest.status = "completed"
    manifest.input_artifacts = [
        artifact_info(warehouse.documents_parquet),
        artifact_info(warehouse.evidence_parquet),
    ]
    manifest.output_artifacts = [
        artifact_info(output / name, base=output) for name in PUBLIC_ANALYSIS_FILES
    ]
    manifest.counts = {
        "documents": len(documents),
        "evidence": len(evidence),
        "observations": len(observations),
        "trend_features": len(features),
        "emerging_roles": len(emerging),
        "job_skill_updates": len(updates),
        "kg_link_deltas": len(deltas),
        "rag_contexts": len(contexts),
    }
    write_json(output / "manifest.json", manifest)
    return {
        "run_id": manifest.run_id,
        "output_dir": str(output),
        "counts": manifest.counts,
        "quality": quality["status"],
        "manifest": str(output / "manifest.json"),
    }


def _validate_kg_references(
    emerging: list[Any], updates: list[Any], deltas: list[Any], kg_index: KGIndex | None
) -> dict[str, Any]:
    if kg_index is None:
        return {"status": "not_applicable", "checked_ids": 0, "unknown_ids": []}
    referenced: set[str] = set()
    for role in emerging:
        referenced.update(
            ability.kg_node_id
            for ability in (*role.required_skills, *role.preferred_skills)
            if ability.kg_node_id
        )
    for update in updates:
        referenced.update(update.kg_job_ids)
        referenced.update(change.kg_node_id for change in update.changes if change.kg_node_id)
    proposed_ids = {delta.source_id for delta in deltas if delta.operation == "propose_node"}
    baseline_ids = set(kg_index.nodes)
    invalid_existing_targets = sorted(
        delta.target_id
        for delta in deltas
        if delta.operation == "link_existing"
        and delta.target_id
        and delta.target_id not in baseline_ids
    )
    proposed_edge_targets = {
        delta.target_id
        for delta in deltas
        if delta.operation == "propose_edge" and delta.target_id
    }
    unknown = sorted(
        (referenced - baseline_ids)
        | set(invalid_existing_targets)
        | (proposed_edge_targets - baseline_ids - proposed_ids)
    )
    if unknown:
        raise ValueError(f"KG delta contains dangling node IDs: {unknown[:8]}")
    return {
        "status": "valid",
        "checked_ids": len(referenced | proposed_edge_targets),
        "proposed_ids": len(proposed_ids),
        "unknown_ids": [],
    }


def _build_rag_contexts(
    candidates: list[EmergingRole],
    evidence: list[Evidence],
    index: HybridEvidenceIndex,
    kg_index: KGIndex | None,
    retrieval_config: Mapping[str, Any],
    *,
    reranker: Any = None,
) -> list[dict[str, Any]]:
    valid_ids = {item.evidence_id for item in evidence}
    contexts: list[dict[str, Any]] = []
    for candidate in candidates:
        query = " ".join(
            [
                candidate.canonical_title,
                *(item.name for item in candidate.required_skills),
                *(item.name for item in candidate.preferred_skills),
            ]
        )
        hits = index.search(
            query,
            dense_top_k=int(retrieval_config.get("dense_top_k", 50)),
            sparse_top_k=int(retrieval_config.get("sparse_top_k", 50)),
            fused_top_k=int(retrieval_config.get("fused_top_k", 50)),
            rerank_top_k=int(retrieval_config.get("rerank_top_k", 8)),
            reranker=reranker,
        )
        hit_ids = [hit.evidence_id for hit in hits]
        graph_contexts: list[dict[str, Any]] = []
        if kg_index is not None:
            node_ids = {
                ability.kg_node_id
                for ability in (*candidate.required_skills, *candidate.preferred_skills)
                if ability.kg_node_id
            }
            for node_id in sorted(node_ids):
                graph_contexts.append(
                    kg_index.neighbors(node_id, hops=int(retrieval_config.get("graph_hops", 2)))
                )
        contexts.append(
            {
                "schema_version": "jobtrend_rag_context_v1",
                "candidate_id": candidate.role_id,
                "query": query,
                "evidence_ids": [item for item in hit_ids if item in valid_ids],
                "hits": [hit.model_dump(mode="json") for hit in hits],
                "graph_contexts": graph_contexts,
                "citation_gate": "valid" if all(item in valid_ids for item in hit_ids) else "invalid",
            }
        )
    return contexts


def read_run_manifest(path: str | Path) -> RunManifest:
    return RunManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def mark_latest_success(runs_root: str | Path, result: Mapping[str, Any]) -> Path:
    root = Path(runs_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(str(result["manifest"])).resolve()
    state = {
        "schema_version": "jobtrend_pipeline_state_v1",
        "last_successful_run_id": result["run_id"],
        "last_successful_output": str(Path(str(result["output_dir"])).resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = root / "latest_success.json"
    write_json(path, state)
    return path


def new_local_run_dir(runs_root: str | Path, prefix: str = "analysis") -> Path:
    now = datetime.now(timezone.utc)
    run_id = stable_id(prefix, now.isoformat(), length=12).replace(":", "-")
    return Path(runs_root).expanduser().resolve() / run_id


def load_rag_candidates(run_dir: str | Path) -> tuple[list[dict[str, Any]], dict[str, Evidence]]:
    root = Path(run_dir)
    candidates = list(read_jsonl(root / "emerging_roles.jsonl"))
    evidence = {
        item.evidence_id: item
        for item in (Evidence.model_validate(row) for row in read_jsonl(root / "evidence.jsonl"))
    }
    context_by_id = {
        str(row["candidate_id"]): list(row.get("evidence_ids") or [])
        for row in read_jsonl(root / "rag_contexts.jsonl")
    }
    for candidate in candidates:
        candidate["evidence_ids"] = context_by_id.get(
            str(candidate.get("role_id")), list(candidate.get("evidence_ids") or [])[:8]
        )
    return candidates, evidence
