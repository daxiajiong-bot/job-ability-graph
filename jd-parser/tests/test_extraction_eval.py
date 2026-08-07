import json
import tempfile
import unittest
from pathlib import Path

from jd_parser.extraction_eval import evaluate_extraction


class ExtractionEvalTest(unittest.TestCase):
    def test_evaluates_evidence_and_rag_recommendation(self):
        profile = {
            "schema_version": "jd_profile_v1",
            "document_id": "JD_EVAL",
            "document_type": "job",
            "title": "NLP算法工程师",
            "responsibilities": ["负责RAG系统建设"],
            "requirements": ["熟练使用Python"],
            "preferred": [],
            "skills": [
                {"name": "RAG", "level": "mentioned", "evidence": "负责RAG系统建设"},
                {"name": "Python", "level": "required", "evidence": "熟练使用Python"},
            ],
            "constraints": {
                "education": {"value": "本科", "evidence": "学历要求：本科"},
                "experience_years": {"value": 2, "evidence": "具备2年以上经验"},
                "location": {"value": "南京", "evidence": "工作地点：南京"},
            },
            "raw_text": "岗位名称：NLP算法工程师\n工作地点：南京\n学历要求：本科\n具备2年以上经验\n负责RAG系统建设\n熟练使用Python",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles = root / "profiles.jsonl"
            profiles.write_text(json.dumps(profile, ensure_ascii=False) + "\n", encoding="utf-8")
            report = evaluate_extraction(profiles, output_dir=root / "out")
            self.assertEqual(report["metrics"]["skill_evidence_support_rate"], 1)
            self.assertTrue((root / "out" / "extraction_eval.json").exists())
            self.assertTrue((root / "out" / "extraction_eval.md").exists())


if __name__ == "__main__":
    unittest.main()

