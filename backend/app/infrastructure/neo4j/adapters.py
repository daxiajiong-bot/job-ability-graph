"""Neo4j adapters for the v3 knowledge graph contract."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from os import getenv
from typing import Any
from uuid import uuid4

from backend.app.domain.entities import KnowledgeGraphSnapshot, Profile, ProfileType, SourceDocument


GRAPH_NODE_LABEL = "JobAbilityGraphSnapshot"
DOCUMENT_LABEL = "SourceDocument"
CANDIDATE_LABEL = "CandidateProfile"
JOB_LABEL = "JobProfile"
SKILL_LABEL = "Skill"
CAPABILITY_LABEL = "Capability"
EVIDENCE_LABEL = "Evidence"

REL_USES_DOCUMENT = "USES_DOCUMENT"
REL_USES_PROFILE = "USES_PROFILE"
REL_DERIVED_FROM = "DERIVED_FROM"
REL_HAS_SKILL = "HAS_SKILL"
REL_REQUIRES_SKILL = "REQUIRES_SKILL"
REL_HAS_CAPABILITY = "HAS_CAPABILITY"
REL_REQUIRES_CAPABILITY = "REQUIRES_CAPABILITY"
REL_BELONGS_TO_CAPABILITY = "BELONGS_TO_CAPABILITY"
REL_SUPPORTED_BY = "SUPPORTED_BY"


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str
    max_path_depth: int
    retrieval_limit: int

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        return cls(
            uri=getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=getenv("NEO4J_USER", "neo4j"),
            password=getenv("NEO4J_PASSWORD", "jobgraph_neo4j_2026"),
            database=getenv("NEO4J_DATABASE", "neo4j"),
            max_path_depth=_env_int("NEO4J_MAX_PATH_DEPTH", 3, minimum=1, maximum=5),
            retrieval_limit=_env_int("NEO4J_RETRIEVAL_LIMIT", 20, minimum=1, maximum=100),
        )


class Neo4jGraphStore:
    """Thin wrapper around the official Neo4j Python driver."""

    def __init__(self, settings: Neo4jSettings) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError(
                "GRAPH_BACKEND=neo4j requires the 'neo4j' Python package. "
                "Install project dependencies with: python3 -m pip install -r requirements.txt"
            ) from exc

        self.settings = settings
        self._driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))
        self._schema_ready = False

    def close(self) -> None:
        self._driver.close()

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._driver.session(**self._session_kwargs()) as session:
            for statement in _schema_statements():
                session.run(statement)
        self._schema_ready = True

    def write_graph(self, payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._driver.session(**self._session_kwargs()) as session:
            session.execute_write(self._write_graph_tx, payload)

    def retrieve_paths(
        self,
        *,
        snapshot_id: str,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]:
        self.ensure_schema()
        relation_filter = [_safe_relation_type(item) for item in relation_types if item.strip()]
        depth = max(1, min(self.settings.max_path_depth, 5))
        statement = f"""
        MATCH (seed)
        WHERE $snapshot_id IN coalesce(seed.graph_ids, [])
          AND (
            (size($seed_ids) > 0 AND seed.id IN $seed_ids)
            OR (
              size($seed_ids) = 0
              AND $query_lc <> ""
              AND any(value IN [
                coalesce(seed.name, ""),
                coalesce(seed.title, ""),
                coalesce(seed.id, ""),
                coalesce(seed.type, ""),
                coalesce(seed.document_type, "")
              ] WHERE toLower(toString(value)) CONTAINS $query_lc)
            )
            OR (size($seed_ids) = 0 AND $query_lc = "")
          )
        WITH DISTINCT seed
        LIMIT $seed_limit
        MATCH path=(seed)-[*1..{depth}]-(target)
        WHERE all(node IN nodes(path) WHERE $snapshot_id IN coalesce(node.graph_ids, []))
          AND (
            size($relation_types) = 0
            OR all(rel IN relationships(path) WHERE type(rel) IN $relation_types)
          )
        RETURN
          [node IN nodes(path) | {{
            element_id: elementId(node),
            id: node.id,
            labels: labels(node),
            properties: properties(node)
          }}] AS nodes,
          [rel IN relationships(path) | {{
            element_id: elementId(rel),
            type: type(rel),
            start_id: startNode(rel).id,
            end_id: endNode(rel).id,
            properties: properties(rel)
          }}] AS relationships
        LIMIT $limit
        """
        params = {
            "snapshot_id": snapshot_id,
            "query_lc": query.strip().lower(),
            "seed_ids": seed_entity_ids,
            "relation_types": relation_filter,
            "seed_limit": self.settings.retrieval_limit,
            "limit": self.settings.retrieval_limit,
        }
        with self._driver.session(**self._session_kwargs()) as session:
            records = session.run(statement, params).data()
        return _retrieval_result(snapshot_id, query, seed_entity_ids, relation_filter, records)

    def _session_kwargs(self) -> dict[str, str]:
        return {"database": self.settings.database} if self.settings.database else {}

    @staticmethod
    def _write_graph_tx(tx: Any, payload: dict[str, Any]) -> None:
        graph_id = payload["snapshot"]["id"]
        tx.run(
            """
            MERGE (node:JobAbilityGraphSnapshot {id: $id})
            SET node += $properties
            SET node.graph_ids =
              CASE
                WHEN node.graph_ids IS NULL THEN [$graph_id]
                WHEN NOT ($graph_id IN node.graph_ids) THEN node.graph_ids + $graph_id
                ELSE node.graph_ids
              END
            """,
            id=graph_id,
            graph_id=graph_id,
            properties=payload["snapshot"]["properties"],
        )
        for label, rows in payload["nodes_by_label"].items():
            _merge_nodes(tx, label, graph_id, rows)
        for group, rows in payload["relationships_by_group"].items():
            start_label, rel_type, end_label = group
            _merge_relationships(tx, start_label, rel_type, end_label, graph_id, rows)


class Neo4jKnowledgeGraphBuilder:
    """Builds the project knowledge graph and persists it in Neo4j."""

    def __init__(self, repository: Any, store: Neo4jGraphStore) -> None:
        self.repository = repository
        self.store = store

    def build(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]:
        documents = [self.repository.get_document(document_id) for document_id in document_ids]
        candidate_profiles = [
            self.repository.get_profile(profile_id, ProfileType.CANDIDATE) for profile_id in candidate_profile_ids
        ]
        job_profiles = [self.repository.get_profile(profile_id, ProfileType.JOB) for profile_id in job_profile_ids]
        for profile in [*candidate_profiles, *job_profiles]:
            if profile.source_document_id not in document_ids:
                documents.append(self.repository.get_document(profile.source_document_id))

        payload = _build_graph_payload(documents, candidate_profiles, job_profiles)
        self.store.write_graph(payload)
        return {
            "state": "available",
            "implementation": "neo4j",
            "nodes": payload["public_nodes"],
            "edges": payload["public_edges"],
        }


class Neo4jGraphRetriever:
    """Retrieves graph paths from Neo4j for GraphRAG-style evidence."""

    def __init__(self, store: Neo4jGraphStore) -> None:
        self.store = store

    def retrieve(
        self,
        graph: KnowledgeGraphSnapshot,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]:
        snapshot_id = _snapshot_store_id(graph)
        return self.store.retrieve_paths(
            snapshot_id=snapshot_id,
            query=query,
            seed_entity_ids=seed_entity_ids,
            relation_types=relation_types,
        )


def _build_graph_payload(
    documents: list[SourceDocument],
    candidate_profiles: list[Profile],
    job_profiles: list[Profile],
) -> dict[str, Any]:
    snapshot_id = f"kg_snapshot_{uuid4().hex}"
    builder = _GraphPayloadBuilder(snapshot_id)
    builder.add_snapshot(len(documents), len(candidate_profiles), len(job_profiles))

    for document in _unique_by_id(documents):
        builder.add_document(document)
    for profile in candidate_profiles:
        builder.add_profile(profile, CANDIDATE_LABEL, "candidate_profile")
    for profile in job_profiles:
        builder.add_profile(profile, JOB_LABEL, "job_profile")

    return builder.payload()


class _GraphPayloadBuilder:
    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        self.nodes_by_key: dict[str, dict[str, Any]] = {}
        self.edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_snapshot(self, document_count: int, candidate_count: int, job_count: int) -> None:
        self.add_node(
            GRAPH_NODE_LABEL,
            self.snapshot_id,
            "graph_snapshot",
            "Job ability graph snapshot",
            {
                "document_count": document_count,
                "candidate_profile_count": candidate_count,
                "job_profile_count": job_count,
                "schema": "position-skill-capability/v1",
            },
        )

    def add_document(self, document: SourceDocument) -> None:
        self.add_node(
            DOCUMENT_LABEL,
            document.id,
            "document",
            document.source.get("external_id") or document.source.get("uri") or document.id,
            {
                "document_type": document.document_type.value,
                "source_system": document.source.get("source_system"),
                "external_id": document.source.get("external_id"),
                "uri": document.source.get("uri"),
                "published_at": document.source.get("published_at"),
                "char_count": len(document.text),
                "content_digest": document.content_digest,
                "created_at": document.created_at,
                "source_json": _json(document.source),
                "metadata_json": _json(document.metadata),
            },
        )
        self.add_edge(GRAPH_NODE_LABEL, self.snapshot_id, REL_USES_DOCUMENT, DOCUMENT_LABEL, document.id, {})

    def add_profile(self, profile: Profile, label: str, node_type: str) -> None:
        self.add_node(
            label,
            profile.id,
            node_type,
            profile.id,
            {
                "profile_type": profile.profile_type.value,
                "source_document_id": profile.source_document_id,
                "state": profile.state,
                "implementation": profile.implementation,
                "created_at": profile.created_at,
                "attributes_json": _json(profile.attributes),
                "warnings_json": _json(profile.warnings),
            },
        )
        self.add_edge(GRAPH_NODE_LABEL, self.snapshot_id, REL_USES_PROFILE, label, profile.id, {})
        self.add_edge(label, profile.id, REL_DERIVED_FROM, DOCUMENT_LABEL, profile.source_document_id, {})
        self._add_profile_skills(profile, label)
        self._add_profile_capabilities(profile, label)
        self._add_profile_evidence(profile, label)

    def _add_profile_skills(self, profile: Profile, profile_label: str) -> None:
        rel_type = REL_HAS_SKILL if profile.profile_type is ProfileType.CANDIDATE else REL_REQUIRES_SKILL
        for item in _items(profile.attributes.get("skills")):
            name = _item_name(item, ["name", "skill", "skill_name", "label", "title", "text"])
            if not name:
                continue
            skill_id = _named_node_id("skill", name)
            properties = _item_properties(item)
            self.add_node(SKILL_LABEL, skill_id, "skill", name, {"name": name, **properties})
            self.add_edge(
                profile_label,
                profile.id,
                rel_type,
                SKILL_LABEL,
                skill_id,
                {
                    "source_profile_id": profile.id,
                    "source_document_id": profile.source_document_id,
                    **properties,
                },
            )
            capability_name = _item_name(item, ["capability", "capability_name", "category", "domain"])
            if capability_name:
                capability_id = _named_node_id("capability", capability_name)
                self.add_node(CAPABILITY_LABEL, capability_id, "capability", capability_name, {"name": capability_name})
                self.add_edge(SKILL_LABEL, skill_id, REL_BELONGS_TO_CAPABILITY, CAPABILITY_LABEL, capability_id, {})

    def _add_profile_capabilities(self, profile: Profile, profile_label: str) -> None:
        rel_type = REL_HAS_CAPABILITY if profile.profile_type is ProfileType.CANDIDATE else REL_REQUIRES_CAPABILITY
        for item in _items(profile.attributes.get("capabilities")):
            name = _item_name(item, ["name", "capability", "capability_name", "label", "title", "text"])
            if not name:
                continue
            capability_id = _named_node_id("capability", name)
            properties = _item_properties(item)
            self.add_node(CAPABILITY_LABEL, capability_id, "capability", name, {"name": name, **properties})
            self.add_edge(
                profile_label,
                profile.id,
                rel_type,
                CAPABILITY_LABEL,
                capability_id,
                {
                    "source_profile_id": profile.id,
                    "source_document_id": profile.source_document_id,
                    **properties,
                },
            )

    def _add_profile_evidence(self, profile: Profile, profile_label: str) -> None:
        for item in _items(profile.evidence):
            evidence_id = _evidence_id(profile.id, item)
            text_preview = _item_name(item, ["text", "quote", "snippet", "span_text", "content"])
            self.add_node(
                EVIDENCE_LABEL,
                evidence_id,
                "evidence",
                evidence_id,
                {
                    "source_profile_id": profile.id,
                    "source_document_id": profile.source_document_id,
                    "text_preview": text_preview[:500] if text_preview else None,
                    "evidence_json": _json(item),
                },
            )
            self.add_edge(profile_label, profile.id, REL_SUPPORTED_BY, EVIDENCE_LABEL, evidence_id, {})

    def add_node(self, label: str, node_id: str, node_type: str, name: str, properties: dict[str, Any]) -> None:
        key = f"{label}:{node_id}"
        safe_properties = _neo4j_properties({"id": node_id, "type": node_type, "name": name, **properties})
        self.nodes_by_key[key] = {
            "label": label,
            "id": node_id,
            "type": node_type,
            "name": name,
            "properties": safe_properties,
        }

    def add_edge(
        self,
        start_label: str,
        start_id: str,
        rel_type: str,
        end_label: str,
        end_id: str,
        properties: dict[str, Any],
    ) -> None:
        key = (start_id, rel_type, end_id)
        self.edges_by_key[key] = {
            "start_label": start_label,
            "start_id": start_id,
            "type": rel_type,
            "end_label": end_label,
            "end_id": end_id,
            "properties": _neo4j_properties(properties),
        }

    def payload(self) -> dict[str, Any]:
        nodes = list(self.nodes_by_key.values())
        edges = list(self.edges_by_key.values())
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            if node["label"] == GRAPH_NODE_LABEL:
                continue
            nodes_by_label.setdefault(node["label"], []).append({"id": node["id"], "properties": node["properties"]})

        relationships_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for edge in edges:
            group = (edge["start_label"], edge["type"], edge["end_label"])
            relationships_by_group.setdefault(group, []).append(
                {
                    "start_id": edge["start_id"],
                    "end_id": edge["end_id"],
                    "properties": edge["properties"],
                }
            )

        snapshot = self.nodes_by_key[f"{GRAPH_NODE_LABEL}:{self.snapshot_id}"]
        return {
            "snapshot": {"id": self.snapshot_id, "properties": snapshot["properties"]},
            "nodes_by_label": nodes_by_label,
            "relationships_by_group": relationships_by_group,
            "public_nodes": [_public_node(node) for node in nodes],
            "public_edges": [_public_edge(edge) for edge in edges],
        }


def _schema_statements() -> list[str]:
    return [
        "CREATE CONSTRAINT job_ability_graph_snapshot_id IF NOT EXISTS "
        "FOR (node:JobAbilityGraphSnapshot) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT source_document_id IF NOT EXISTS "
        "FOR (node:SourceDocument) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT candidate_profile_id IF NOT EXISTS "
        "FOR (node:CandidateProfile) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT job_profile_id IF NOT EXISTS FOR (node:JobProfile) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (node:Skill) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT capability_id IF NOT EXISTS FOR (node:Capability) REQUIRE node.id IS UNIQUE",
        "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (node:Evidence) REQUIRE node.id IS UNIQUE",
    ]


def _merge_nodes(tx: Any, label: str, graph_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = f"""
    UNWIND $rows AS row
    MERGE (node:{_identifier(label)} {{id: row.id}})
    SET node += row.properties
    SET node.graph_ids =
      CASE
        WHEN node.graph_ids IS NULL THEN [$graph_id]
        WHEN NOT ($graph_id IN node.graph_ids) THEN node.graph_ids + $graph_id
        ELSE node.graph_ids
      END
    """
    tx.run(statement, rows=rows, graph_id=graph_id)


def _merge_relationships(
    tx: Any,
    start_label: str,
    rel_type: str,
    end_label: str,
    graph_id: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    statement = f"""
    UNWIND $rows AS row
    MATCH (start:{_identifier(start_label)} {{id: row.start_id}})
    MATCH (end:{_identifier(end_label)} {{id: row.end_id}})
    MERGE (start)-[rel:{_identifier(rel_type)}]->(end)
    SET rel += row.properties
    SET rel.graph_ids =
      CASE
        WHEN rel.graph_ids IS NULL THEN [$graph_id]
        WHEN NOT ($graph_id IN rel.graph_ids) THEN rel.graph_ids + $graph_id
        ELSE rel.graph_ids
      END
    """
    tx.run(statement, rows=rows, graph_id=graph_id)


def _retrieval_result(
    snapshot_id: str,
    query: str,
    seed_entity_ids: list[str],
    relation_types: list[str],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    entities: dict[str, dict[str, Any]] = {}
    paths: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        nodes = record.get("nodes", [])
        relationships = record.get("relationships", [])
        for node in nodes:
            node_id = str(node.get("id") or node.get("element_id"))
            entities[node_id] = node
        paths.append(
            {
                "id": f"path_{index + 1}",
                "nodes": nodes,
                "relationships": relationships,
                "length": len(relationships),
            }
        )
    return {
        "state": "available",
        "implementation": "neo4j",
        "graph_store_id": snapshot_id,
        "query": query,
        "seed_entity_ids": seed_entity_ids,
        "relation_types": relation_types,
        "entities": list(entities.values()),
        "paths": paths,
    }


def _snapshot_store_id(graph: KnowledgeGraphSnapshot) -> str:
    for node in graph.nodes:
        if node.get("type") == "graph_snapshot":
            return str(node["id"])
    return graph.id


def _unique_by_id(documents: list[SourceDocument]) -> list[SourceDocument]:
    unique: dict[str, SourceDocument] = {}
    for document in documents:
        unique[document.id] = document
    return list(unique.values())


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _item_name(item: Any, keys: list[str]) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _item_properties(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    allowed = {
        "level",
        "proficiency",
        "importance",
        "weight",
        "confidence",
        "years",
        "category",
        "domain",
        "source",
        "evidence_id",
        "evidence_ids",
    }
    return {key: value for key, value in item.items() if key in allowed}


def _named_node_id(prefix: str, name: str) -> str:
    digest = sha256(name.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _evidence_id(profile_id: str, item: Any) -> str:
    if isinstance(item, dict) and item.get("id"):
        raw = f"{profile_id}:{item['id']}"
    else:
        raw = f"{profile_id}:{_json(item)}"
    return f"evidence_{sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _neo4j_properties(properties: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            safe[key] = value
        else:
            safe[f"{key}_json"] = _json(value)
    return safe


def _public_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node["id"],
        "type": node["type"],
        "labels": [node["label"]],
        "name": node["name"],
        "properties": node["properties"],
    }


def _public_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{edge['start_id']}:{edge['type']}:{edge['end_id']}",
        "source": edge["start_id"],
        "target": edge["end_id"],
        "type": edge["type"],
        "properties": edge["properties"],
    }


def _identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"unsafe Cypher identifier: {name}")
    return f"`{name}`"


def _safe_relation_type(value: str) -> str:
    relation_type = value.strip().upper()
    _identifier(relation_type)
    return relation_type


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))
