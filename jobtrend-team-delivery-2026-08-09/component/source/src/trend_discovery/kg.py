"""Read-only adapters for the team's two knowledge-graph exports.

Importing a graph writes only a small index manifest into this project's
warehouse.  The source graph is fingerprinted and subsequently opened
read-only; source node identifiers are never regenerated or rewritten.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .dedup import normalize_text, normalize_title
from .io_utils import read_jsonl, sha256_file, sha256_text, write_json
from .schemas import AbilityCategory, AbilityRef


INDEX_FILE = "kg_index.json"
ABILITY_LABELS = {"Skill", "Ability", "Knowledge", "Technology", "Transversal", "Language"}
ABILITY_CATEGORIES: set[str] = {"K", "S", "Tech", "T", "L", "Skill", "unknown"}


def _resolved_file(path: str | Path, *, required: bool = True) -> Path:
    value = Path(path).expanduser().resolve()
    if required and (not value.is_file()):
        raise FileNotFoundError(value)
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def _detect_schema(nodes: list[dict[str, Any]], profiles_path: Path | None) -> str:
    if profiles_path is not None:
        for row in read_jsonl(profiles_path):
            version = str(row.get("schema_version") or "")
            if version == "jd_profile_v1":
                return "jd_kg_v1"
            if version.startswith("small-raw-") or "lskt-tech/v2" in version:
                return "small-raw-lskt-tech/v2"
            break
    for node in nodes:
        properties = node.get("properties") or {}
        if node.get("label") == "Skill" and properties.get("category") in {"K", "S", "Tech", "T", "L"}:
            return "small-raw-lskt-tech/v2"
    return "jd_kg_v1"


def _bundle_fingerprint(files: Iterable[tuple[str, Path]]) -> tuple[str, dict[str, str]]:
    hashes = {label: sha256_file(path) for label, path in files}
    fingerprint = sha256_text("\n".join(f"{key}:{hashes[key]}" for key in sorted(hashes)))
    return fingerprint, hashes


def import_kg_bundle(
    nodes_path: str | Path,
    edges_path: str | Path,
    profiles_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate/fingerprint a KG bundle and write a read-only index manifest.

    ``output_dir`` is intentionally required for normal operation, but may be
    omitted by callers that only want validation/fingerprinting.  No source
    file is opened for writing.
    """

    nodes_file = _resolved_file(nodes_path)
    edges_file = _resolved_file(edges_path)
    profiles_file = _resolved_file(profiles_path) if profiles_path is not None else None
    nodes = _read_rows(nodes_file)
    edges = _read_rows(edges_file)

    node_ids: set[str] = set()
    duplicate_node_ids: list[str] = []
    for row in nodes:
        node_id = row.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(f"{nodes_file}: node without a non-empty node_id")
        if node_id in node_ids:
            duplicate_node_ids.append(node_id)
        node_ids.add(node_id)
    if duplicate_node_ids:
        raise ValueError(f"{nodes_file}: duplicate node IDs: {sorted(set(duplicate_node_ids))[:5]}")

    edge_ids: set[str] = set()
    duplicate_edge_ids: list[str] = []
    dangling: list[str] = []
    for row in edges:
        edge_id = row.get("edge_id")
        if not isinstance(edge_id, str) or not edge_id:
            raise ValueError(f"{edges_file}: edge without a non-empty edge_id")
        if edge_id in edge_ids:
            duplicate_edge_ids.append(edge_id)
        edge_ids.add(edge_id)
        if row.get("source_id") not in node_ids or row.get("target_id") not in node_ids:
            dangling.append(edge_id)
    if duplicate_edge_ids:
        raise ValueError(f"{edges_file}: duplicate edge IDs: {sorted(set(duplicate_edge_ids))[:5]}")
    if dangling:
        raise ValueError(f"{edges_file}: dangling edges: {dangling[:5]}")

    files: list[tuple[str, Path]] = [("nodes", nodes_file), ("edges", edges_file)]
    if profiles_file is not None:
        files.append(("profiles", profiles_file))
    fingerprint, hashes = _bundle_fingerprint(files)
    source_schema = _detect_schema(nodes, profiles_file)
    ability_count = sum(1 for row in nodes if _is_ability_node(row))
    job_count = sum(1 for row in nodes if row.get("label") == "Job")
    manifest: dict[str, Any] = {
        "schema_version": "jobtrend_kg_index_v1",
        "source_schema": source_schema,
        "fingerprint": fingerprint,
        "files": {
            "nodes": str(nodes_file),
            "edges": str(edges_file),
            "profiles": str(profiles_file) if profiles_file else None,
        },
        "file_sha256": hashes,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "jobs": job_count,
            "abilities": ability_count,
        },
        "validation": {"status": "valid", "dangling_edges": 0},
    }
    if output_dir is not None:
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / INDEX_FILE, manifest)
    return manifest


def _is_ability_node(node: Mapping[str, Any]) -> bool:
    label = str(node.get("label") or "")
    properties = node.get("properties") or {}
    return label in ABILITY_LABELS or (
        label == "Skill" and str(properties.get("category") or "") in ABILITY_CATEGORIES
    )


def _node_name(node: Mapping[str, Any]) -> str:
    properties = node.get("properties") or {}
    for key in ("name", "canonical_name", "normalized_name", "title", "label", "value"):
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(node.get("node_id") or "")


def _node_aliases(node: Mapping[str, Any]) -> list[str]:
    properties = node.get("properties") or {}
    values = properties.get("aliases") or properties.get("alias") or []
    if isinstance(values, str):
        values = [values]
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _node_category(node: Mapping[str, Any]) -> AbilityCategory:
    properties = node.get("properties") or {}
    value = str(properties.get("category") or "")
    if value in ABILITY_CATEGORIES:
        return value  # type: ignore[return-value]
    label = str(node.get("label") or "")
    mapping = {
        "Knowledge": "K",
        "Skill": "Skill",
        "Technology": "Tech",
        "Transversal": "T",
        "Language": "L",
    }
    return mapping.get(label, "unknown")  # type: ignore[return-value]


def _char_terms(value: str) -> set[str]:
    value = re.sub(r"\s+", "", normalize_text(value))
    if len(value) < 2:
        return {value} if value else set()
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _name_similarity(left: str, right: str) -> float:
    left_norm, right_norm = normalize_text(left), normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm, autojunk=False).ratio()
    left_terms, right_terms = _char_terms(left_norm), _char_terms(right_norm)
    union = left_terms | right_terms
    jaccard = len(left_terms & right_terms) / len(union) if union else 0.0
    return max(sequence, 0.55 * sequence + 0.45 * jaccard)


class KGIndex:
    """In-memory read-only view over a versioned graph bundle."""

    def __init__(
        self,
        *,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        fingerprint: str,
        source_schema: str,
        curated_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.nodes = {str(row["node_id"]): row for row in nodes}
        self.edges = tuple(edges)
        self.fingerprint = fingerprint
        self.source_schema = source_schema
        self.curated_aliases = {
            normalize_text(alias): str(target) for alias, target in (curated_aliases or {}).items()
        }
        self._adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for edge in edges:
            source_id, target_id = str(edge["source_id"]), str(edge["target_id"])
            self._adjacency[source_id].append((target_id, edge))
            self._adjacency[target_id].append((source_id, edge))
        self._abilities = sorted(
            (row for row in nodes if _is_ability_node(row)), key=lambda row: str(row["node_id"])
        )
        self._jobs = sorted(
            (row for row in nodes if row.get("label") == "Job"), key=lambda row: str(row["node_id"])
        )
        self._job_names: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self._jobs:
            self._job_names[normalize_title(_node_name(node))].append(node)
        self._ability_names: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self._abilities:
            self._ability_names[normalize_text(_node_name(node))].append(node)
            for alias in _node_aliases(node):
                # Aliases embedded in the baseline are treated as curated by
                # the graph producer, not as semantic automatic matches.
                self.curated_aliases.setdefault(normalize_text(alias), str(node["node_id"]))
        self._ability_resolution_cache: dict[tuple[str, float], AbilityRef] = {}
        self._job_search_cache: dict[tuple[str, int], tuple[dict[str, Any], ...]] = {}
        self._job_ability_cache: dict[str, tuple[str, ...]] = {}

    @classmethod
    def load(
        cls,
        output_dir: str | Path,
        *,
        curated_aliases: Mapping[str, str] | None = None,
    ) -> "KGIndex":
        path = Path(output_dir).expanduser().resolve()
        manifest_path = path if path.is_file() else path / INDEX_FILE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "jobtrend_kg_index_v1":
            raise ValueError(f"{manifest_path}: unsupported KG index schema")
        files = manifest["files"]
        nodes_path, edges_path = Path(files["nodes"]), Path(files["edges"])
        # Detect source mutation after import.  Silently accepting it would
        # make graph deltas impossible to audit.
        current_fingerprint, _ = _bundle_fingerprint(
            [("nodes", nodes_path), ("edges", edges_path)]
            + ([("profiles", Path(files["profiles"]))] if files.get("profiles") else [])
        )
        if current_fingerprint != manifest["fingerprint"]:
            raise ValueError("knowledge graph files changed after import; import a new baseline")
        return cls(
            nodes=_read_rows(nodes_path),
            edges=_read_rows(edges_path),
            fingerprint=str(manifest["fingerprint"]),
            source_schema=str(manifest["source_schema"]),
            curated_aliases=curated_aliases,
        )

    @classmethod
    def from_files(
        cls,
        nodes_path: str | Path,
        edges_path: str | Path,
        profiles_path: str | Path | None = None,
        *,
        curated_aliases: Mapping[str, str] | None = None,
    ) -> "KGIndex":
        manifest = import_kg_bundle(nodes_path, edges_path, profiles_path)
        return cls(
            nodes=_read_rows(_resolved_file(nodes_path)),
            edges=_read_rows(_resolved_file(edges_path)),
            fingerprint=str(manifest["fingerprint"]),
            source_schema=str(manifest["source_schema"]),
            curated_aliases=curated_aliases,
        )

    @property
    def ability_nodes(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._abilities)

    @property
    def job_nodes(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._jobs)

    def neighbors(self, node_id: str, hops: int = 2) -> dict[str, Any]:
        """Return the induced undirected 1- or 2-hop evidence subgraph."""

        if node_id not in self.nodes:
            raise KeyError(node_id)
        if hops not in (1, 2):
            raise ValueError("hops must be 1 or 2")
        visited = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        touched_edges: dict[str, dict[str, Any]] = {}
        while queue:
            current, distance = queue.popleft()
            if distance >= hops:
                continue
            for adjacent, edge in self._adjacency.get(current, []):
                touched_edges[str(edge["edge_id"])] = edge
                if adjacent not in visited:
                    visited.add(adjacent)
                    queue.append((adjacent, distance + 1))
        return {
            "center_id": node_id,
            "hops": hops,
            "nodes": [self.nodes[value] for value in sorted(visited)],
            "edges": [touched_edges[value] for value in sorted(touched_edges)],
        }

    def _ability_ref(
        self,
        node: Mapping[str, Any] | None,
        status: str,
        *,
        query: str,
        score: float | None,
    ) -> AbilityRef:
        if node is None:
            return AbilityRef(
                source_schema=self.source_schema,
                canonical_name=query.strip(),
                category="unknown",
                resolution_status="unresolved",
                resolution_score=score,
            )
        return AbilityRef(
            source_schema=self.source_schema,
            source_node_id=str(node["node_id"]),
            category=_node_category(node),
            canonical_name=_node_name(node),
            aliases=_node_aliases(node),
            resolution_status=status,  # type: ignore[arg-type]
            resolution_score=score,
        )

    def resolve_ability(self, name: str, *, semantic_threshold: float = 0.62) -> AbilityRef:
        """Resolve only exact/case-folded and explicitly curated aliases.

        A semantic match is returned as ``review_candidate`` and must never be
        used as an automatic graph link.
        """

        query = name.strip()
        normal = normalize_text(query)
        cache_key = (normal, float(semantic_threshold))
        cached = self._ability_resolution_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(deep=True)
        exact = self._ability_names.get(normal)
        if exact:
            result = self._ability_ref(exact[0], "exact", query=query, score=1.0)
            self._ability_resolution_cache[cache_key] = result
            return result.model_copy(deep=True)
        target = self.curated_aliases.get(normal)
        if target:
            if target in self.nodes and _is_ability_node(self.nodes[target]):
                result = self._ability_ref(self.nodes[target], "curated_alias", query=query, score=1.0)
                self._ability_resolution_cache[cache_key] = result
                return result.model_copy(deep=True)
            candidates = self._ability_names.get(normalize_text(target))
            if candidates:
                result = self._ability_ref(candidates[0], "curated_alias", query=query, score=1.0)
                self._ability_resolution_cache[cache_key] = result
                return result.model_copy(deep=True)
        candidates = self.search_abilities(query, limit=1, semantic_threshold=semantic_threshold)
        result = candidates[0] if candidates else self._ability_ref(None, "unresolved", query=query, score=0.0)
        self._ability_resolution_cache[cache_key] = result
        return result.model_copy(deep=True)

    def search_abilities(
        self,
        query: str,
        limit: int = 10,
        *,
        semantic_threshold: float = 0.0,
    ) -> list[AbilityRef]:
        if limit <= 0:
            return []
        scored = sorted(
            ((_name_similarity(query, _node_name(node)), node) for node in self._abilities),
            key=lambda value: (-value[0], str(value[1]["node_id"])),
        )
        results: list[AbilityRef] = []
        for score, node in scored:
            if score < semantic_threshold:
                continue
            exact = normalize_text(query) == normalize_text(_node_name(node))
            status = "exact" if exact else "review_candidate"
            results.append(self._ability_ref(node, status, query=query, score=score))
            if len(results) >= limit:
                break
        return results

    def search_jobs(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        cache_key = (normalize_title(query), int(limit))
        cached = self._job_search_cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        exact_nodes = self._job_names.get(cache_key[0])
        if exact_nodes:
            result = [
                {
                    "node_id": str(node["node_id"]),
                    "canonical_title": _node_name(node),
                    "score": 1.0,
                }
                for node in exact_nodes[:limit]
            ]
            self._job_search_cache[cache_key] = tuple(result)
            return [dict(item) for item in result]
        scored = sorted(
            (
                (_name_similarity(normalize_title(query), normalize_title(_node_name(node))), node)
                for node in self._jobs
            ),
            key=lambda value: (-value[0], str(value[1]["node_id"])),
        )
        result = [
            {
                "node_id": str(node["node_id"]),
                "canonical_title": _node_name(node),
                "score": float(score),
            }
            for score, node in scored[:limit]
        ]
        self._job_search_cache[cache_key] = tuple(result)
        return [dict(item) for item in result]

    def job_ability_names(self, job_node_id: str) -> tuple[str, ...]:
        """Return one-hop baseline abilities for a job prototype."""

        if job_node_id not in self.nodes or self.nodes[job_node_id].get("label") != "Job":
            raise KeyError(job_node_id)
        cached = self._job_ability_cache.get(job_node_id)
        if cached is not None:
            return cached
        names = sorted(
            {
                _node_name(self.nodes[adjacent])
                for adjacent, edge in self._adjacency.get(job_node_id, [])
                if adjacent in self.nodes
                and _is_ability_node(self.nodes[adjacent])
                and str(edge.get("relation_type") or "").startswith(("REQUIRES_", "PREFERS_", "MENTIONS_"))
            }
        )
        result = tuple(names)
        self._job_ability_cache[job_node_id] = result
        return result


__all__ = ["INDEX_FILE", "KGIndex", "import_kg_bundle"]
