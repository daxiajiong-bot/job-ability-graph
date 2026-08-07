"""Mocks that expose future seams without producing fake intelligence."""

from __future__ import annotations

from typing import Any

from backend.app.domain.entities import KnowledgeGraphSnapshot, MatchAssessment, Profile, ProfileType, SourceDocument
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION


NOT_IMPLEMENTED = "not_implemented"


def _mock(reason: str, **payload: Any) -> dict[str, Any]:
    return {
        "state": NOT_IMPLEMENTED,
        "implementation": "mock",
        "reason": reason,
        **payload,
    }


class MockStructuredExtractor:
    def extract(self, document: SourceDocument) -> dict[str, Any]:
        return _mock("Structured extraction is reserved for a future local LLM.", fields={}, evidence=[])


class MockSkillNormalizer:
    def normalize(self, extraction: dict[str, Any]) -> dict[str, Any]:
        return _mock("Skill normalization is not configured.", skills=[])


class MockProfileBuilder:
    def build(
        self,
        profile_type: ProfileType,
        document: SourceDocument,
        extraction: dict[str, Any],
        normalization: dict[str, Any],
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "profile_schema": PROFILE_SCHEMA_VERSION,
            "skills": [],
            "capabilities": [],
            "experience": [],
            "education": [],
            "projects": [],
        }
        if profile_type is ProfileType.JOB:
            attributes.update({"job": {}, "job_title": None, "requirements": [], "responsibilities": [], "jd_profile": {}})
        else:
            attributes.update({"candidate": {}, "career_intent": {}, "target_position": None, "resume_profile": {}})
        return _mock(
            "Profile construction is reserved for structured extraction and normalization adapters.",
            attributes=attributes,
            evidence=[],
            warnings=["No extraction, normalization, or inference has been performed."],
        )


class MockDocumentRetriever:
    def retrieve(self, query: str, document_ids: list[str], filters: dict[str, Any]) -> dict[str, Any]:
        return _mock("Document RAG is not configured.", query=query, document_ids=document_ids, evidence=[])


class MockKnowledgeGraphBuilder:
    def build(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]:
        return _mock("Neo4j graph construction is not configured.", nodes=[], edges=[])


class SQLiteKnowledgeGraphBuilder:
    """Builds knowledge graph from pre-built graph data files."""

    def __init__(self, repository: Any, data_root: str | None = None) -> None:
        self.repository = repository
        self.data_root = data_root or "data"

    def build(
        self,
        document_ids: list[str],
        candidate_profile_ids: list[str],
        job_profile_ids: list[str],
    ) -> dict[str, Any]:
        import json as _json
        from pathlib import Path

        # Try to load pre-built graph data
        graph_dir = Path(self.data_root) / "small_raw_200_lskt_tech_v2"
        nodes_file = graph_dir / "graph_nodes.jsonl"
        edges_file = graph_dir / "graph_edges.jsonl"

        if not nodes_file.exists() or not edges_file.exists():
            return _mock("Graph data files not found.", nodes=[], edges=[])

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_ids: set[str] = set()

        # Load nodes
        with open(nodes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    node = _json.loads(line)
                    label = node.get("label", "")
                    if label in ("Job", "Skill", "Technology", "Company"):
                        nodes.append(node)
                        node_ids.add(node["node_id"])
                except _json.JSONDecodeError:
                    continue

        # Load edges
        with open(edges_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    edge = _json.loads(line)
                    source = edge.get("source_id", "")
                    target = edge.get("target_id", "")
                    relation = edge.get("relation_type", "")
                    if source in node_ids and target in node_ids:
                        if relation in ("REQUIRES_SKILL", "REQUIRES_TECHNOLOGY", "BELONGS_TO_CAPABILITY"):
                            edges.append(edge)
                except _json.JSONDecodeError:
                    continue

        if not nodes:
            return _mock("No valid nodes found in graph data.", nodes=[], edges=[])

        # Limit to reasonable size for frontend rendering
        if len(nodes) > 500:
            kept_ids = {n["node_id"] for n in nodes[:500]}
            nodes = nodes[:500]
            edges = [e for e in edges if e.get("source_id") in kept_ids and e.get("target_id") in kept_ids]

        return {
            "state": "available",
            "implementation": "prebuilt_graph",
            "nodes": nodes,
            "edges": edges,
        }


class MockGraphRetriever:
    def retrieve(
        self,
        graph: KnowledgeGraphSnapshot,
        query: str,
        seed_entity_ids: list[str],
        relation_types: list[str],
    ) -> dict[str, Any]:
        return _mock("GraphRAG is not configured.", query=query, entities=[], paths=[])


class MockPositionEvolution:
    def discover(self, document_ids: list[str], options: dict[str, Any]) -> dict[str, Any]:
        return _mock(
            "New-position discovery is not configured.",
            document_ids=document_ids,
            candidate_positions=[],
            evidence=[],
        )

    def delta(
        self,
        baseline: Profile,
        current: Profile,
        supporting_document_ids: list[str],
    ) -> dict[str, Any]:
        return _mock(
            "Position evolution analysis is not configured.",
            baseline_job_profile_id=baseline.id,
            current_job_profile_id=current.id,
            added=[],
            removed=[],
            changed=[],
            evidence=[],
        )


class MockMatcher:
    def assess(self, candidate: Profile, job: Profile, options: dict[str, Any]) -> dict[str, Any]:
        return _mock(
            "Graph-enhanced person-job matching is not configured.",
            score=None,
            decision="not_evaluated",
            strengths=[],
            gaps=[],
            learning_path=[],
            document_evidence=[],
            graph_evidence=[],
        )


class MockReportGenerator:
    def generate(self, match: MatchAssessment, language: str) -> dict[str, Any]:
        return _mock("Report generation is reserved for a future local LLM.", sections=[])


class MockLearningAdvisor:
    def generate(self, match_data: dict[str, Any]) -> dict[str, Any]:
        score = match_data.get("score", 0)
        gaps = match_data.get("gaps", [])
        learning_path = match_data.get("learning_path", [])

        # Build mock skill gaps from match gaps
        skill_gaps = []
        for gap in gaps[:5]:
            skill_gaps.append({
                "skill": gap.get("text", gap.get("skill", "未知技能")),
                "current_level": "初级",
                "target_level": "中级",
                "priority": gap.get("importance", "medium"),
                "learning_steps": [
                    f"学习{gap.get('text', gap.get('skill', '该技能'))}的基础概念",
                    "通过实际项目练习巩固",
                    "参与开源项目或完成在线课程",
                ],
                "resources": ["官方文档", "在线教程"],
                "estimated_time": "2-4周",
            })

        # Build mock learning plan
        learning_plan = [
            {
                "phase": "第一阶段：基础补齐",
                "duration": "2-4周",
                "goals": ["掌握核心技能基础", "完成入门练习"],
                "activities": ["阅读官方文档", "完成在线课程", "动手实践"],
            },
            {
                "phase": "第二阶段：项目实战",
                "duration": "4-8周",
                "goals": ["独立完成项目", "积累实战经验"],
                "activities": ["参与开源项目", "完成个人项目", "代码审查"],
            },
        ]

        return {
            "state": "available",
            "implementation": "mock_learning_advisor",
            "summary": f"当前匹配度为 {score}%，建议重点提升岗位要求的核心技能",
            "skill_gaps": skill_gaps,
            "learning_plan": learning_plan,
            "recommended_resources": [
                {"type": "documentation", "name": "技术官方文档", "description": "学习相关技术的官方文档"},
                {"type": "course", "name": "在线学习平台", "description": "系统学习相关课程"},
                {"type": "practice", "name": "实战项目", "description": "通过实际项目提升技能"},
            ],
            "career_advice": "建议制定系统的学习计划，优先补齐核心技能差距，同时保持已有优势的持续提升。",
            "warnings": ["Mock 数据（后端使用模拟数据）"],
        }


def capability_catalog(
    *,
    structured_extraction_implementation: str = "mock",
    structured_extraction_state: str = NOT_IMPLEMENTED,
    skill_normalization_implementation: str = "mock",
    skill_normalization_state: str = NOT_IMPLEMENTED,
    profile_builder_implementation: str = "mock",
    profile_builder_state: str = NOT_IMPLEMENTED,
    knowledge_graph_implementation: str = "mock",
    knowledge_graph_state: str = NOT_IMPLEMENTED,
    graph_rag_implementation: str = "mock",
    graph_rag_state: str = NOT_IMPLEMENTED,
    matching_implementation: str = "mock",
    matching_state: str = NOT_IMPLEMENTED,
    report_generation_implementation: str = "mock",
    report_generation_state: str = NOT_IMPLEMENTED,
) -> list[dict[str, str]]:
    return [
        {"name": "document_repository", "implementation": "memory", "state": "available"},
        {"name": "ocr", "implementation": "paddleocr", "state": "available"},
        {"name": "data_governance", "implementation": "filesystem", "state": "available"},
        {"name": "data_governance_rag", "implementation": "lexical_chunk_retrieval", "state": "available"},
        {
            "name": "structured_extraction",
            "implementation": structured_extraction_implementation,
            "state": structured_extraction_state,
        },
        {
            "name": "skill_normalization",
            "implementation": skill_normalization_implementation,
            "state": skill_normalization_state,
        },
        {
            "name": "profile_builder",
            "implementation": profile_builder_implementation,
            "state": profile_builder_state,
        },
        {"name": "document_rag", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {"name": "knowledge_graph", "implementation": knowledge_graph_implementation, "state": knowledge_graph_state},
        {"name": "graph_rag", "implementation": graph_rag_implementation, "state": graph_rag_state},
        {"name": "position_evolution", "implementation": "mock", "state": NOT_IMPLEMENTED},
        {
            "name": "matching",
            "implementation": matching_implementation,
            "state": matching_state,
        },
        {
            "name": "report_generation",
            "implementation": report_generation_implementation,
            "state": report_generation_state,
        },
    ]
