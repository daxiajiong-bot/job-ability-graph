from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from backend.app.domain.entities import DocumentType, KnowledgeGraphSnapshot, Profile, ProfileType, SourceDocument
from backend.app.infrastructure.neo4j.adapters import Neo4jKnowledgeGraphBuilder, _query_terms
from backend.app.infrastructure.sqlite.db import DatabaseManager
from backend.app.infrastructure.sqlite.repository import SQLiteResourceRepository


class FakeRepository:
    def __init__(self, documents: list[SourceDocument], profiles: list[Profile]) -> None:
        self.documents = {document.id: document for document in documents}
        self.profiles = {profile.id: profile for profile in profiles}

    def get_document(self, document_id: str) -> SourceDocument:
        return self.documents[document_id]

    def get_profile(self, profile_id: str, expected_type: ProfileType | None = None) -> Profile:
        profile = self.profiles[profile_id]
        if expected_type is not None:
            self.assert_profile_type(profile, expected_type)
        return profile

    @staticmethod
    def assert_profile_type(profile: Profile, expected_type: ProfileType) -> None:
        if profile.profile_type is not expected_type:
            raise AssertionError(f"expected {expected_type}, got {profile.profile_type}")


class FakeStore:
    def __init__(self) -> None:
        self.payload = None

    def write_graph(self, payload):
        self.payload = payload


class Neo4jAdapterTest(unittest.TestCase):
    def test_graph_query_terms_support_natural_language_questions(self) -> None:
        terms = _query_terms("Python 开发岗位需要哪些技能和知识？")

        self.assertIn("python", terms)
        self.assertTrue(any(term in terms for term in ("开发", "技能", "知识")))
        self.assertNotIn("需要", terms)

    def test_sqlite_repository_persists_graph_snapshot_for_retrieval(self) -> None:
        with TemporaryDirectory() as tempdir:
            manager = DatabaseManager(Path(tempdir) / "app.db")
            repository = SQLiteResourceRepository(manager)
            graph = KnowledgeGraphSnapshot.create(
                ["doc-1"],
                [],
                [],
                {
                    "state": "available",
                    "implementation": "neo4j",
                    "nodes": [{"id": "snapshot-1", "type": "graph_snapshot"}],
                    "edges": [],
                },
            )

            repository.add_graph(graph)
            restored = repository.get_graph(graph.id)

            self.assertEqual(restored.id, graph.id)
            self.assertEqual(restored.nodes, graph.nodes)
            self.assertEqual(restored.implementation, "neo4j")
            manager.close()

    def test_builder_maps_profiles_to_graph_payload(self) -> None:
        resume = SourceDocument.create(
            DocumentType.RESUME,
            "candidate text",
            {"source_system": "unit-test", "external_id": "resume-1"},
            {},
        )
        jd = SourceDocument.create(
            DocumentType.JD,
            "job text",
            {"source_system": "unit-test", "external_id": "jd-1"},
            {},
        )
        candidate = Profile.create(
            ProfileType.CANDIDATE,
            resume.id,
            {
                "state": "available",
                "implementation": "unit-test",
                "attributes": {
                    "skills": [{"name": "Python", "capability": "Data analysis", "level": "advanced"}],
                    "capabilities": [{"name": "Data analysis", "confidence": 0.9}],
                },
                "evidence": [{"id": "ev-1", "text": "candidate used Python in a project"}],
            },
        )
        job = Profile.create(
            ProfileType.JOB,
            jd.id,
            {
                "state": "available",
                "implementation": "unit-test",
                "attributes": {
                    "skills": [{"name": "Python", "capability": "Data analysis", "importance": "required"}],
                    "capabilities": [{"name": "Data analysis"}],
                },
                "evidence": [{"id": "ev-2", "text": "job requires Python"}],
            },
        )
        store = FakeStore()
        repository = FakeRepository([resume, jd], [candidate, job])

        result = Neo4jKnowledgeGraphBuilder(repository, store).build([], [candidate.id], [job.id])

        self.assertEqual(result["state"], "available")
        self.assertEqual(result["implementation"], "neo4j")
        node_types = {node["type"] for node in result["nodes"]}
        self.assertIn("graph_snapshot", node_types)
        self.assertIn("document", node_types)
        self.assertIn("candidate_profile", node_types)
        self.assertIn("job_profile", node_types)
        self.assertIn("skill", node_types)
        self.assertIn("capability", node_types)
        self.assertIn("evidence", node_types)

        relation_types = {edge["type"] for edge in result["edges"]}
        self.assertIn("HAS_SKILL", relation_types)
        self.assertIn("REQUIRES_SKILL", relation_types)
        self.assertIn("BELONGS_TO_CAPABILITY", relation_types)
        self.assertIn("SUPPORTED_BY", relation_types)
        self.assertIsNotNone(store.payload)
        self.assertIn("Skill", store.payload["nodes_by_label"])
        self.assertIn(("CandidateProfile", "HAS_SKILL", "Skill"), store.payload["relationships_by_group"])


if __name__ == "__main__":
    unittest.main()
