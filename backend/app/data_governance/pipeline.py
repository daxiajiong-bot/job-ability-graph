"""Deterministic data governance pipeline from raw files to graph and RAG artifacts."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

from backend.app.data_governance.lskt import SpanExtractor, validate_candidate
from backend.app.data_governance.schemas import (
    Chunk,
    EntityCandidate,
    Evidence,
    GraphEdge,
    GraphNode,
    ParsedDocument,
    QualityReport,
    RelationCandidate,
)
from backend.app.data_governance.store import DataGovernanceStore
from backend.app.domain.entities import utc_now


class DataGovernancePipeline:
    def __init__(self, store: DataGovernanceStore, span_extractor: SpanExtractor) -> None:
        self.store = store
        self.span_extractor = span_extractor

    def process(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        metadata = self.store.get_metadata(doc_id, version)
        raw_text, parser_name, parse_warnings = self.store.read_raw_text(metadata)
        cleaned_text = clean_text(raw_text)
        quality = self._quality_report(metadata.doc_id, metadata.version, raw_text, cleaned_text, parse_warnings)
        parsed = ParsedDocument(
            doc_id=metadata.doc_id,
            version=metadata.version,
            document_type=metadata.document_type,
            parser=parser_name,
            raw_path=metadata.raw_path,
            content_hash=metadata.content_hash,
            text=cleaned_text,
            sections=_detect_sections(cleaned_text),
            warnings=parse_warnings,
            created_at=utc_now(),
        )
        chunks = chunk_text(parsed)
        entity_candidates = self._extract_entities(parsed, chunks)
        relation_candidates = self._relations(metadata.document_type, metadata.doc_id, metadata.version, entity_candidates)
        nodes, edges = self._graph(metadata.document_type, parsed, chunks, entity_candidates, relation_candidates)

        paths = {
            "quality": self.store.write_quality(quality),
            "parsed": self.store.write_json("staging", metadata.doc_id, metadata.version, "parsed_document.json", parsed.to_dict()),
            "chunks_staging": self.store.write_jsonl(
                "staging", metadata.doc_id, metadata.version, "chunks.jsonl", [chunk.to_dict() for chunk in chunks]
            ),
            "entity_candidates": self.store.write_jsonl(
                "staging",
                metadata.doc_id,
                metadata.version,
                "entity_candidates.jsonl",
                [candidate.to_dict() for candidate in entity_candidates],
            ),
            "relation_candidates": self.store.write_jsonl(
                "staging",
                metadata.doc_id,
                metadata.version,
                "relation_candidates.jsonl",
                [candidate.to_dict() for candidate in relation_candidates],
            ),
            "entities": self.store.write_jsonl(
                "structured",
                metadata.doc_id,
                metadata.version,
                "entities.jsonl",
                [candidate.to_dict() for candidate in entity_candidates],
            ),
            "relations": self.store.write_jsonl(
                "structured",
                metadata.doc_id,
                metadata.version,
                "relations.jsonl",
                [candidate.to_dict() for candidate in relation_candidates],
            ),
            "graph": self.store.write_json(
                "graph",
                metadata.doc_id,
                metadata.version,
                "graph.json",
                {
                    "doc_id": metadata.doc_id,
                    "version": metadata.version,
                    "nodes": [node.to_dict() for node in nodes],
                    "edges": [edge.to_dict() for edge in edges],
                },
            ),
            "rag_chunks": self.store.write_jsonl(
                "rag", metadata.doc_id, metadata.version, "chunks.jsonl", [rag_chunk(chunk, entity_candidates) for chunk in chunks]
            ),
        }
        return {
            "doc_id": metadata.doc_id,
            "version": metadata.version,
            "status": "processed",
            "quality": quality.to_dict(),
            "counts": {
                "chunks": len(chunks),
                "entity_candidates": len(entity_candidates),
                "relation_candidates": len(relation_candidates),
                "graph_nodes": len(nodes),
                "graph_edges": len(edges),
            },
            "artifacts": paths,
        }

    def _quality_report(
        self,
        doc_id: str,
        version: int,
        raw_text: str,
        cleaned_text: str,
        warnings: list[str],
    ) -> QualityReport:
        checks = [
            {"name": "raw_text_present", "passed": bool(raw_text.strip()), "value": len(raw_text)},
            {"name": "cleaned_text_present", "passed": bool(cleaned_text.strip()), "value": len(cleaned_text)},
            {"name": "doc_id_required", "passed": bool(doc_id), "value": doc_id},
            {"name": "version_positive", "passed": version > 0, "value": version},
        ]
        status = "passed" if all(check["passed"] for check in checks) and not warnings else "warning"
        if not cleaned_text.strip():
            status = "failed"
        return QualityReport(doc_id=doc_id, version=version, status=status, checks=checks, warnings=warnings, created_at=utc_now())

    def _extract_entities(self, parsed: ParsedDocument, chunks: list[Chunk]) -> list[EntityCandidate]:
        candidates: list[EntityCandidate] = []
        sequence = 0
        for chunk in chunks:
            for span in self.span_extractor.extract(chunk.text):
                if not validate_candidate(chunk.text, span):
                    continue
                sequence += 1
                evidence = _evidence(parsed, chunk, span.start_char, span.end_char, sequence)
                if span.surface not in evidence.quote:
                    continue
                normalized_id = skill_node_id(span.normalized_name, span.esco_uri)
                candidates.append(
                    EntityCandidate(
                        entity_candidate_id=f"ent_{parsed.doc_id}_v{parsed.version}_{sequence:04d}",
                        doc_id=parsed.doc_id,
                        version=parsed.version,
                        chunk_id=chunk.chunk_id,
                        entity_type="skill",
                        surface=span.surface,
                        normalized_name=span.normalized_name,
                        normalized_id=normalized_id,
                        category=span.category,
                        lskt_label=span.lskt_label,
                        start_char=chunk.start_char + span.start_char,
                        end_char=chunk.start_char + span.end_char,
                        confidence=span.confidence,
                        extraction_method=span.extraction_method,
                        evidence=evidence,
                        created_at=utc_now(),
                        esco_id=span.esco_id,
                        esco_uri=span.esco_uri,
                        esco_preferred_label=span.esco_preferred_label,
                        esco_version=span.esco_version,
                        linking_status=span.linking_status,
                        linking_confidence=span.linking_confidence,
                        normalization_status=span.normalization_status,
                    )
                )
        return candidates

    def _relations(
        self,
        document_type: str,
        doc_id: str,
        version: int,
        entities: list[EntityCandidate],
    ) -> list[RelationCandidate]:
        relation_type = {
            "jd": "REQUIRES_SKILL",
            "resume": "HAS_SKILL",
            "policy": "MENTIONS_SKILL",
            "industry_report": "MENTIONS_SKILL",
            "market_data": "MENTIONS_SKILL",
        }.get(document_type, "MENTIONS_SKILL")
        relations: list[RelationCandidate] = []
        seen: set[tuple[str, str]] = set()
        for index, entity in enumerate(entities, start=1):
            key = (relation_type, entity.normalized_id)
            if key in seen:
                continue
            seen.add(key)
            relations.append(
                RelationCandidate(
                    relation_candidate_id=f"rel_{doc_id}_v{version}_{index:04d}",
                    doc_id=doc_id,
                    version=version,
                    source_id=document_node_id(doc_id, version),
                    target_id=entity.normalized_id,
                    relation_type=relation_type,
                    confidence=entity.confidence,
                    evidence=entity.evidence,
                    validation_status="validated_with_span_and_evidence",
                    created_at=utc_now(),
                )
            )
        return relations

    def _graph(
        self,
        document_type: str,
        parsed: ParsedDocument,
        chunks: list[Chunk],
        entities: list[EntityCandidate],
        relations: list[RelationCandidate],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        now = utc_now()
        document_id = document_node_id(parsed.doc_id, parsed.version)
        nodes = [
            GraphNode(
                node_id=document_id,
                doc_id=parsed.doc_id,
                version=parsed.version,
                label="Document",
                properties={
                    "document_type": document_type,
                    "content_hash": parsed.content_hash,
                    "raw_path": parsed.raw_path,
                    "parser": parsed.parser,
                },
                created_at=now,
            )
        ]
        edges: list[GraphEdge] = []
        for chunk in chunks:
            chunk_node_id = chunk_node_id_for(chunk)
            nodes.append(
                GraphNode(
                    node_id=chunk_node_id,
                    doc_id=parsed.doc_id,
                    version=parsed.version,
                    label="Chunk",
                    properties={
                        "chunk_id": chunk.chunk_id,
                        "sequence": chunk.sequence,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                    },
                    created_at=now,
                )
            )
            evidence = chunk_edge_evidence(chunk)
            edges.append(
                GraphEdge(
                    edge_id=f"edge_{parsed.doc_id}_v{parsed.version}_contains_{chunk.sequence:04d}",
                    doc_id=parsed.doc_id,
                    version=parsed.version,
                    source_id=document_id,
                    target_id=chunk_node_id,
                    relation_type="CONTAINS_CHUNK",
                    evidence_ids=[evidence.evidence_id],
                    evidence=[evidence],
                    properties={"sequence": chunk.sequence},
                    created_at=now,
                )
            )
        skill_nodes: dict[str, GraphNode] = {}
        for entity in entities:
            skill_nodes.setdefault(
                entity.normalized_id,
                GraphNode(
                    node_id=entity.normalized_id,
                    doc_id=parsed.doc_id,
                    version=parsed.version,
                    label="Skill",
                    properties={
                        "name": entity.normalized_name,
                        "category": entity.category,
                        "lskt_label": entity.lskt_label,
                        "esco_id": entity.esco_id,
                        "esco_uri": entity.esco_uri,
                        "esco_preferred_label": entity.esco_preferred_label,
                        "esco_version": entity.esco_version,
                        "linking_status": entity.linking_status,
                        "linking_confidence": entity.linking_confidence,
                        "normalization_status": entity.normalization_status,
                    },
                    created_at=now,
                ),
            )
        nodes.extend(skill_nodes.values())
        evidence_nodes: dict[str, GraphNode] = {}
        for relation in relations:
            evidence_nodes[relation.evidence.evidence_id] = GraphNode(
                node_id=relation.evidence.evidence_id,
                doc_id=parsed.doc_id,
                version=parsed.version,
                label="Evidence",
                properties=relation.evidence.to_dict(),
                created_at=now,
            )
            edges.append(
                GraphEdge(
                    edge_id=f"edge_{relation.relation_candidate_id}",
                    doc_id=parsed.doc_id,
                    version=parsed.version,
                    source_id=relation.source_id,
                    target_id=relation.target_id,
                    relation_type=relation.relation_type,
                    evidence_ids=[relation.evidence.evidence_id],
                    evidence=[relation.evidence],
                    properties={
                        "validation_status": relation.validation_status,
                        "confidence": relation.confidence,
                        "lskt_label": _entity_label(entities, relation.target_id),
                        "linking_status": _entity_linking_status(entities, relation.target_id),
                    },
                    created_at=now,
                )
            )
        nodes.extend(evidence_nodes.values())
        return nodes, edges


def clean_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(parsed: ParsedDocument, max_chars: int = 800, overlap: int = 80) -> list[Chunk]:
    text = parsed.text
    if not text:
        return []
    chunks: list[Chunk] = []
    start = 0
    sequence = 1
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end), text.rfind("；", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk_body = text[start:end].strip()
        leading_trim = len(text[start:end]) - len(text[start:end].lstrip())
        adjusted_start = start + leading_trim
        adjusted_end = adjusted_start + len(chunk_body)
        chunks.append(
            Chunk(
                chunk_id=f"{parsed.doc_id}_v{parsed.version}_chunk_{sequence:04d}",
                doc_id=parsed.doc_id,
                version=parsed.version,
                sequence=sequence,
                text=chunk_body,
                start_char=adjusted_start,
                end_char=adjusted_end,
                content_hash=parsed.content_hash,
                raw_path=parsed.raw_path,
                created_at=utc_now(),
            )
        )
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        sequence += 1
    return chunks


def rag_chunk(chunk: Chunk, entities: list[EntityCandidate]) -> dict[str, Any]:
    chunk_entities = [entity for entity in entities if entity.chunk_id == chunk.chunk_id]
    return {
        **chunk.to_dict(),
        "skills": sorted({entity.normalized_name for entity in chunk_entities}),
        "competency_spans": [
            {
                "surface": entity.surface,
                "normalized_name": entity.normalized_name,
                "lskt_label": entity.lskt_label,
                "category": entity.category,
                "start_char": entity.start_char,
                "end_char": entity.end_char,
                "evidence_id": entity.evidence.evidence_id,
                "esco_uri": entity.esco_uri,
                "esco_preferred_label": entity.esco_preferred_label,
                "esco_version": entity.esco_version,
                "linking_status": entity.linking_status,
                "linking_confidence": entity.linking_confidence,
            }
            for entity in chunk_entities
        ],
        "lskt_labels": sorted({entity.lskt_label for entity in chunk_entities if entity.lskt_label}),
        "evidence_ids": [entity.evidence.evidence_id for entity in chunk_entities],
    }


def document_node_id(doc_id: str, version: int) -> str:
    return f"document:{doc_id}:v{version}"


def chunk_node_id_for(chunk: Chunk) -> str:
    return f"chunk:{chunk.chunk_id}"


def skill_node_id(name: str, esco_uri: str | None = None) -> str:
    if esco_uri:
        return f"skill:{esco_uri}"
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", name.strip().casefold()).strip("_")
    digest = sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"skill:emerging:{slug or digest}"


def chunk_edge_evidence(chunk: Chunk) -> Evidence:
    quote = chunk.text[:200]
    return Evidence(
        evidence_id=f"ev_{chunk.doc_id}_v{chunk.version}_chunk_{chunk.sequence:04d}",
        doc_id=chunk.doc_id,
        version=chunk.version,
        chunk_id=chunk.chunk_id,
        quote=quote,
        start_char=chunk.start_char,
        end_char=min(chunk.start_char + len(quote), chunk.end_char),
        source_field="chunk_text",
        raw_path=chunk.raw_path,
        content_hash=chunk.content_hash,
        created_at=utc_now(),
    )


def _evidence(parsed: ParsedDocument, chunk: Chunk, local_start: int, local_end: int, sequence: int) -> Evidence:
    quote_start = max(0, local_start - 80)
    quote_end = min(len(chunk.text), local_end + 80)
    quote = chunk.text[quote_start:quote_end].strip()
    return Evidence(
        evidence_id=f"ev_{parsed.doc_id}_v{parsed.version}_{sequence:04d}",
        doc_id=parsed.doc_id,
        version=parsed.version,
        chunk_id=chunk.chunk_id,
        quote=quote,
        start_char=chunk.start_char + quote_start,
        end_char=chunk.start_char + quote_start + len(quote),
        source_field="chunk_text",
        raw_path=parsed.raw_path,
        content_hash=parsed.content_hash,
        created_at=utc_now(),
    )


def _overlaps(left: range, right: range) -> bool:
    return left.start < right.stop and right.start < left.stop


def _entity_label(entities: list[EntityCandidate], target_id: str) -> str | None:
    for entity in entities:
        if entity.normalized_id == target_id:
            return entity.lskt_label
    return None


def _entity_linking_status(entities: list[EntityCandidate], target_id: str) -> str | None:
    for entity in entities:
        if entity.normalized_id == target_id:
            return entity.linking_status
    return None


def _detect_sections(text: str) -> list[dict[str, Any]]:
    headings = ("岗位职责", "任职要求", "工作经历", "项目经历", "教育背景", "政策要求", "报告摘要")
    sections: list[dict[str, Any]] = []
    for heading in headings:
        index = text.find(heading)
        if index >= 0:
            sections.append({"title": heading, "start_char": index})
    return sorted(sections, key=lambda item: item["start_char"])
