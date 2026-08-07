from __future__ import annotations

import unittest

from backend.app.domain.entities import DocumentType
from backend.app.domain.profile_schemas import (
    PROFILE_SCHEMA_VERSION,
    ProfileSchemaError,
    normalize_profile_payload,
)


def _resume_payload() -> dict:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": "resume",
        "candidate": {"name": "张三", "current_title": "算法工程师"},
        "career_intent": {"target_position": "大模型算法工程师"},
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "skills": [
            {
                "name": "Python",
                "raw_name": "Python",
                "category": "programming_language",
                "lskt_label": "S",
                "level": "proficient",
                "evidence_text": "熟练使用 Python",
            }
        ],
        "capabilities": [],
        "certificates": [],
        "languages": [],
        "achievements": [],
    }


def _jd_payload() -> dict:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "document_type": "jd",
        "job": {"title": "AI????????", "normalized_title": "AI????????"},
        "company": {"name": "??????", "industry": "AI", "location": "??"},
        "employment": {"employment_type": "full_time", "salary_min": None, "salary_max": None, "published_at": None},
        "responsibilities": [
            {
                "text": "?????????",
                "action": "??",
                "object": "???????",
                "evidence_text": "?????????",
            }
        ],
        "requirements": [
            {
                "text": "??Prompt??",
                "requirement_type": "skill",
                "importance": "required",
                "evidence_text": "??Prompt??",
            }
        ],
        "skills": [],
        "capabilities": [],
        "application_scenarios": [
            {
                "name": "????",
                "description": "?????????",
                "evidence_text": "?????????",
            }
        ],
        "evaluation_signals": [
            {
                "name": "????",
                "description": "???????????",
                "evidence_text": "???????????",
            }
        ],
    }


class ProfileSchemasTest(unittest.TestCase):
    def test_resume_payload_is_normalized_with_legacy_aliases(self) -> None:
        payload = normalize_profile_payload(
            _resume_payload(),
            DocumentType.RESUME,
            source_text="张三，算法工程师，熟练使用 Python，目标大模型算法工程师。",
        )

        self.assertEqual(payload["schema_version"], PROFILE_SCHEMA_VERSION)
        self.assertEqual(payload["experience"], [])
        self.assertEqual(payload["projects"], [])
        self.assertEqual(payload["responsibilities"], [])
        self.assertEqual(payload["skills"][0]["evidence_ids"], ["ev_001"])
        self.assertNotIn("evidence_text", payload["skills"][0])
        self.assertEqual(payload["evidence"], [{"id": "ev_001", "field": "skills", "text": "熟练使用 Python"}])

    def test_keeps_evidence_not_copied_from_source(self) -> None:
        raw_payload = _resume_payload()
        raw_payload["skills"].append(
            {
                "name": "Java",
                "raw_name": "Java",
                "category": "programming_language",
                "lskt_label": "S",
                "level": "familiar",
                "evidence_text": "???? Java",
            }
        )
        payload = normalize_profile_payload(
            raw_payload,
            DocumentType.RESUME,
            source_text="????????????? Python????????????",
        )

        self.assertEqual([item["name"] for item in payload["skills"]], ["Python", "Java"])
        self.assertEqual([item["evidence_ids"] for item in payload["skills"]], [["ev_001"], ["ev_002"]])
        self.assertEqual(len(payload["evidence"]), 2)
        self.assertEqual(payload["evidence"][0]["id"], "ev_001")
        self.assertEqual(payload["evidence"][1]["id"], "ev_002")
        self.assertTrue(payload["evidence"][0]["text"].endswith("Python"))
        self.assertTrue(payload["evidence"][1]["text"].endswith("Java"))
        self.assertEqual(payload["_warnings"], [])

    def test_auto_generates_missing_evidence_text(self) -> None:
        payload = _resume_payload()
        payload["skills"].append(
            {
                "name": "Java",
                "raw_name": "Java",
                "category": "programming_language",
                "lskt_label": "S",
                "level": "familiar",
            }
        )

        normalized = normalize_profile_payload(
            payload,
            DocumentType.RESUME,
            source_text="????????????? Python????????????",
        )

        self.assertEqual([item["name"] for item in normalized["skills"]], ["Python", "Java"])
        self.assertEqual([item["evidence_ids"] for item in normalized["skills"]], [["ev_001"], ["ev_002"]])
        self.assertEqual(len(normalized["evidence"]), 2)
        self.assertEqual(normalized["evidence"][0]["id"], "ev_001")
        self.assertEqual(normalized["evidence"][1]["id"], "ev_002")
        self.assertTrue(normalized["evidence"][0]["text"].endswith("Python"))
        self.assertTrue(normalized["evidence"][1]["text"].endswith("Java"))
        self.assertEqual(normalized["_warnings"], [])

    def test_missing_jd_list_fields_are_defaulted(self) -> None:
        payload = _jd_payload()
        payload.pop("evaluation_signals")

        normalized = normalize_profile_payload(
            payload,
            DocumentType.JD,
            source_text="????????????Prompt?????????????????????????",
        )

        self.assertEqual(normalized["evaluation_signals"], [])
        self.assertTrue(any("evaluation_signals" in warning for warning in normalized["_warnings"]))


if __name__ == "__main__":
    unittest.main()
