import json
import tempfile
import unittest
from pathlib import Path

from jd_parser.rag import run_rag_augmentation


class RagAugmentationTest(unittest.TestCase):
    def test_adds_only_grounded_candidate(self):
        base = {
            "schema_version": "jd_profile_v1",
            "document_id": "JD_BASE",
            "document_type": "job",
            "title": "算法工程师",
            "responsibilities": [],
            "requirements": ["熟悉Python"],
            "preferred": [],
            "skills": [{"name": "Python", "level": "required", "evidence": "熟悉Python"}],
            "constraints": {"education": {}, "experience_years": {}, "location": {}},
            "raw_text": "岗位名称：算法工程师\n熟悉Python",
        }
        target = {
            "schema_version": "jd_profile_v1",
            "document_id": "JD_TARGET",
            "document_type": "job",
            "title": "AI应用工程师",
            "responsibilities": ["负责RAG系统开发"],
            "requirements": [],
            "preferred": [],
            "skills": [],
            "constraints": {"education": {}, "experience_years": {}, "location": {}},
            "raw_text": "岗位名称：AI应用工程师\n负责RAG系统开发",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles = root / "profiles.jsonl"
            profiles.write_text(
                json.dumps(base, ensure_ascii=False) + "\n" + json.dumps(target, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            summary = run_rag_augmentation(profiles, root / "out")
            self.assertGreaterEqual(summary["added_skill_mentions"], 1)
            out = (root / "out" / "profiles.jsonl").read_text(encoding="utf-8")
            self.assertIn("RAG", out)
            self.assertNotIn("FAISS", out)


if __name__ == "__main__":
    unittest.main()

