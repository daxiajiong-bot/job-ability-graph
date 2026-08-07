import json
import tempfile
import unittest
from pathlib import Path

from jd_parser.kg import build_graph


class KnowledgeGraphTest(unittest.TestCase):
    def test_builds_graph_with_evidence(self):
        profile = {
            "schema_version": "jd_profile_v1",
            "document_id": "JD_TEST",
            "document_type": "job",
            "title": "NLP算法工程师",
            "responsibilities": ["负责RAG系统建设"],
            "requirements": ["熟练使用Python"],
            "preferred": ["有知识图谱经验者优先"],
            "skills": [
                {"name": "RAG", "level": "mentioned", "evidence": "负责RAG系统建设"},
                {"name": "Python", "level": "required", "evidence": "熟练使用Python"},
                {"name": "知识图谱", "level": "preferred", "evidence": "有知识图谱经验者优先"},
            ],
            "constraints": {
                "education": {"value": "本科", "evidence": "学历要求：本科"},
                "experience_years": {"value": 2, "evidence": "具备2年以上经验"},
                "location": {"value": "南京", "evidence": "工作地点：南京"},
            },
            "raw_text": "岗位名称：NLP算法工程师\n工作地点：南京\n学历要求：本科\n具备2年以上经验\n负责RAG系统建设\n熟练使用Python\n有知识图谱经验者优先",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles_path = root / "profiles.jsonl"
            profiles_path.write_text(json.dumps(profile, ensure_ascii=False) + "\n", encoding="utf-8")
            summary = build_graph(profiles_path, root / "kg")
            self.assertEqual(summary["validation_status"], "valid")
            self.assertEqual(summary["source_profile_count"], 1)
            edges = (root / "kg" / "graph_edges.jsonl").read_text(encoding="utf-8")
            self.assertIn("REQUIRES_SKILL", edges)
            self.assertIn("SUPPORTED_BY", edges)


if __name__ == "__main__":
    unittest.main()

