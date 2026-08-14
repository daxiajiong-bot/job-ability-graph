"""Seed loader: reads jd_raw.jsonl and inserts system-level JD documents."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Optional

from backend.app.infrastructure.sqlite.db import DatabaseManager


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_initial_jds(db: DatabaseManager, jsonl_path: str | Path, batch_size: int = 500) -> int:
    """
    Load JD records from a JSONL file into the documents table as system data.
    Returns the number of records inserted. Skips if system JDs already exist.
    """
    existing = db.execute(
        "SELECT COUNT(*) FROM documents WHERE user_id = 'system' AND document_type = 'jd'"
    ).fetchone()
    if existing and existing[0] > 0:
        return 0  # Already seeded

    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        return 0

    # Ensure the 'system' user exists (required for foreign key)
    now = _utc_now_iso()
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, created_at, last_active_at) VALUES ('system', ?, ?)",
        (now, now),
    )
    db.commit()

    inserted = 0
    batch: list[tuple] = []
    now = _utc_now_iso()

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            doc_id = f"sys_jd_{record.get('job_id', '')}"
            jd_text = record.get("jd_text", "")
            content_digest = sha256(jd_text.encode("utf-8")).hexdigest()

            # Build salary range string
            salary_min = record.get("salary_min", "0")
            salary_max = record.get("salary_max", "0")
            if salary_min and salary_max and salary_min != "0" and salary_max != "0":
                salary_range = f"{salary_min}-{salary_max}"
            else:
                salary_range = None

            # Skills as JSON array
            skills = record.get("skills_norm") or record.get("skills_raw") or []
            skills_json = json.dumps(skills, ensure_ascii=False)

            # Extra metadata
            metadata = {
                "source_type": record.get("source_type"),
                "source_name": record.get("source_name"),
                "page": record.get("page"),
                "publish_date": record.get("publish_date"),
                "scrape_time": record.get("scrape_time"),
                "responsibilities": record.get("responsibilities"),
                "requirements": record.get("requirements"),
                "skills_raw": record.get("skills_raw"),
            }

            batch.append((
                doc_id,
                "system",          # user_id
                "jd",              # document_type
                jd_text,           # text
                record.get("job_title"),
                record.get("company_name"),
                record.get("industry"),
                record.get("location"),
                salary_range,
                record.get("experience"),
                record.get("education"),
                skills_json,
                record.get("source_name", "zhaopin"),
                str(record.get("job_id", "")),
                record.get("url"),
                json.dumps(metadata, ensure_ascii=False),
                content_digest,
                now,
            ))

            if len(batch) >= batch_size:
                _insert_batch(db, batch)
                inserted += len(batch)
                batch = []

    if batch:
        _insert_batch(db, batch)
        inserted += len(batch)

    db.commit()
    return inserted


def _insert_batch(db: DatabaseManager, batch: list[tuple]) -> None:
    db.executemany(
        """INSERT OR IGNORE INTO documents
           (id, user_id, document_type, text, title, company_name, industry,
            location, salary_range, experience, education, skills,
            source_system, source_id, url, metadata, content_digest, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        batch,
    )


def get_seed_status(db: DatabaseManager) -> dict[str, int]:
    """Check how many system JDs are loaded."""
    row = db.execute(
        "SELECT COUNT(*) FROM documents WHERE user_id = 'system' AND document_type = 'jd'"
    ).fetchone()
    return {"system_jd_count": row[0] if row else 0}


PREBUILT_GRAPH_ID = "kg_prebuilt_v2"


def ensure_prebuilt_graph(repository, data_root: str | Path) -> bool:
    """Register the pre-built knowledge graph as a queryable snapshot.

    Loads ``small_raw_200_lskt_tech_v2`` (also imported into Neo4j by
    ``scripts/import_prebuilt_kg.py``) into the repository so that
    ``GET /api/v1/knowledge-graphs/kg_prebuilt_v2`` returns real graph data and
    ``POST /api/v1/graph-retrievals`` (graph_id=kg_prebuilt_v2) queries Neo4j.

    Returns True when the snapshot was registered, False when it already
    existed or the graph files were missing.
    """
    from backend.app.domain.entities import KnowledgeGraphSnapshot

    if hasattr(repository, "get_graph"):
        try:
            repository.get_graph(PREBUILT_GRAPH_ID)
            return False  # already registered
        except Exception:
            pass

    graph_dir = Path(data_root) / "small_raw_200_lskt_tech_v2"
    nodes_file = graph_dir / "graph_nodes.jsonl"
    edges_file = graph_dir / "graph_edges.jsonl"
    if not nodes_file.exists() or not edges_file.exists():
        return False

    nodes: list[dict] = []
    for line in nodes_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            node = json.loads(line)
        except json.JSONDecodeError:
            continue
        node_id = node.get("node_id", "")
        label = node.get("label", "")
        props = dict(node.get("properties") or {})
        name = props.get("name") or props.get("title") or node_id
        nodes.append({"id": node_id, "label": label, "type": label, "name": name, "properties": props})

    edges: list[dict] = []
    for line in edges_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            edge = json.loads(line)
        except json.JSONDecodeError:
            continue
        edges.append({
            "source": edge.get("source_id", ""),
            "target": edge.get("target_id", ""),
            "type": edge.get("relation_type", ""),
            "relation_type": edge.get("relation_type", ""),
            "evidence_ids": edge.get("evidence_ids", []),
            "properties": dict(edge.get("properties") or {}),
        })

    snapshot = KnowledgeGraphSnapshot(
        id=PREBUILT_GRAPH_ID,
        document_ids=[],
        candidate_profile_ids=[],
        job_profile_ids=[],
        nodes=nodes,
        edges=edges,
        state="available",
        implementation="neo4j",
        created_at=_utc_now_iso(),
    )
    repository.add_graph(snapshot)
    return True
