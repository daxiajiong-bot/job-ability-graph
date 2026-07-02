from __future__ import annotations

import unittest

from backend.app.infrastructure.llm.normalization import normalize_skills


class SkillNormalizationTest(unittest.TestCase):
    def test_exact_esco_alt_label_links_python(self) -> None:
        skills = normalize_skills(
            [
                {
                    "name": "Python",
                    "raw_name": "Python",
                    "category": "programming_language",
                    "evidence_ids": ["ev_001"],
                }
            ]
        )

        self.assertEqual(skills[0]["name"], "Python (computer programming)")
        self.assertEqual(skills[0]["linking_status"], "linked")
        self.assertEqual(skills[0]["linking_confidence"], 1.0)
        self.assertTrue(skills[0]["esco_uri"].startswith("http://data.europa.eu/esco/skill/"))

    def test_non_exact_matches_are_not_hard_linked(self) -> None:
        skills = normalize_skills(
            [
                {"name": "Java", "raw_name": "Java", "category": "programming_language", "evidence_ids": ["ev_001"]},
                {"name": "C/C++", "raw_name": "C/C++", "category": "programming_language", "evidence_ids": ["ev_002"]},
                {"name": "数据分析", "raw_name": "数据分析", "category": "data_processing", "evidence_ids": ["ev_003"]},
            ]
        )

        by_raw_name = {skill["raw_name"]: skill for skill in skills}
        self.assertNotEqual(by_raw_name["Java"]["esco_preferred_label"], "JavaScript")
        self.assertEqual(by_raw_name["Java"]["esco_preferred_label"], "Java (computer programming)")
        self.assertNotEqual(by_raw_name["C/C++"]["esco_preferred_label"], "English")
        self.assertEqual(by_raw_name["C/C++"]["linking_status"], "unmapped")
        self.assertEqual(by_raw_name["数据分析"]["name"], "数据分析")
        self.assertEqual(by_raw_name["数据分析"]["linking_status"], "unmapped")
        self.assertEqual(by_raw_name["数据分析"]["linking_confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
