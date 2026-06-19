from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.app.algorithms.job_intelligence import compare_job_versions, discover_emerging_job
from backend.app.algorithms.panorama_graph import build_panorama_graph
from backend.app.algorithms.pipeline import match_jd_resume, parse_jd, parse_resume
from backend.app.api.router import samples
from backend.app.input_adapters.document_text import DocumentExtractionError, extract_text_from_bytes
from backend.app.main import app
from scripts.evaluate_demo import evaluate


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DemoPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jd_samples = json.loads((PROJECT_ROOT / "data" / "samples" / "jd_samples.json").read_text(encoding="utf-8"))
        cls.resume_samples = json.loads((PROJECT_ROOT / "data" / "samples" / "resume_samples.json").read_text(encoding="utf-8"))

    def test_parse_jd_is_independent(self) -> None:
        result = parse_jd(self.jd_samples[0]["text"])
        self.assertEqual(result["mode"], "jd_parse")
        self.assertEqual(result["jd_parse"]["job_title"], "大模型算法工程师")
        skill_names = {skill["name"] for skill in result["job_profile"]["skills"]}
        self.assertIn("RAG", skill_names)
        self.assertIn("大语言模型", skill_names)

    def test_parse_resume_is_independent(self) -> None:
        result = parse_resume(self.resume_samples[0]["text"])
        self.assertEqual(result["mode"], "resume_parse")
        self.assertEqual(result["resume_parse"]["candidate_id"], "候选人A")
        skill_names = {skill["name"] for skill in result["resume_profile"]["skills"]}
        self.assertIn("Python", skill_names)
        self.assertIn("RAG", skill_names)

    def test_match_returns_score_and_graph(self) -> None:
        result = match_jd_resume(self.jd_samples[0]["text"], self.resume_samples[0]["text"])
        self.assertGreaterEqual(result["match_result"]["final_score"], 75)
        self.assertGreater(len(result["graph"]["nodes"]), 0)
        self.assertGreater(len(result["graph"]["edges"]), 0)

    def test_job_update_detects_added_skills(self) -> None:
        old_text = self.jd_samples[1]["text"]
        new_text = old_text + "\n新增要求:\n熟悉 RAG、大语言模型、知识图谱 和 Kubernetes 者优先。"
        result = compare_job_versions(old_text, new_text)
        added_names = {skill["name"] for skill in result["ability_changes"]["added_skills"]}
        self.assertIn("RAG", added_names)
        self.assertIn("大语言模型", added_names)
        self.assertIn("知识图谱", added_names)

    def test_emerging_job_discovery_uses_sources(self) -> None:
        result = discover_emerging_job(
            [
                {"source_id": self.jd_samples[0]["id"], "text": self.jd_samples[0]["text"], "reliability": 0.8},
                {"source_id": self.jd_samples[1]["id"], "text": self.jd_samples[1]["text"], "reliability": 0.8},
            ]
        )
        self.assertEqual(result["mode"], "emerging_job_discovery")
        self.assertEqual(result["draft_job_definition"]["source_count"], 2)
        self.assertGreater(len(result["draft_job_definition"]["required_skills"]), 0)
        self.assertTrue(result["competition_hooks"]["supports_emerging_job_discovery"])

    def test_evaluation_script_metrics(self) -> None:
        result = evaluate(
            PROJECT_ROOT / "data" / "evaluation" / "demo_eval_cases.json",
            PROJECT_ROOT / "data" / "samples" / "jd_samples.json",
            PROJECT_ROOT / "data" / "samples" / "resume_samples.json",
        )
        self.assertGreaterEqual(result["metrics"]["jd_parse_accuracy"], 0.9)
        self.assertGreaterEqual(result["metrics"]["resume_parse_accuracy"], 0.9)
        self.assertGreaterEqual(result["metrics"]["match_accuracy"], 0.9)

    def test_resume_text_document_adapter_is_decoupled(self) -> None:
        source_text = self.resume_samples[0]["text"]
        document = extract_text_from_bytes(source_text.encode("utf-8"), filename="resume.txt")
        self.assertEqual(document.metadata["extension"], ".txt")
        parsed = parse_resume(document.text)
        self.assertEqual(parsed["resume_parse"]["candidate_id"], "候选人A")

    def test_document_adapter_rejects_unsupported_type(self) -> None:
        with self.assertRaises(DocumentExtractionError):
            extract_text_from_bytes(b"hello", filename="resume.xls")

    def test_panorama_graph_builds_stack_and_level_views(self) -> None:
        graph = build_panorama_graph(self.jd_samples)
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertEqual(graph["mode"], "job_skill_panorama_graph")
        self.assertIn("Job", node_types)
        self.assertIn("Skill", node_types)
        self.assertIn("by_skill_type", graph["views"])
        self.assertIn("by_level", graph["views"])
        self.assertTrue(graph["graph_metadata"]["competition_hooks"]["supports_panorama_graph"])

    def test_backend_exposes_visualization_and_samples(self) -> None:
        paths = {route.path for route in app.routes if hasattr(route, "path")}
        self.assertIn("/", paths)
        self.assertIn("/samples", paths)
        self.assertIn("/graph/panorama", paths)
        payload = samples()
        self.assertGreaterEqual(len(payload["jds"]), 4)
        self.assertGreaterEqual(len(payload["resumes"]), 4)


if __name__ == "__main__":
    unittest.main()
