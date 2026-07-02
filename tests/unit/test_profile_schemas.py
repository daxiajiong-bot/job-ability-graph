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

    def test_drops_evidence_not_copied_from_source(self) -> None:
        raw_payload = _resume_payload()
        raw_payload["skills"].append(
            {
                "name": "Java",
                "raw_name": "Java",
                "category": "programming_language",
                "lskt_label": "S",
                "level": "familiar",
                "evidence_text": "熟练使用 Java",
            }
        )
        payload = normalize_profile_payload(
            raw_payload,
            DocumentType.RESUME,
            source_text="张三，算法工程师，熟练使用 Python，目标大模型算法工程师。",
        )

        self.assertEqual([item["name"] for item in payload["skills"]], ["Python"])
        self.assertEqual(payload["evidence"], [{"id": "ev_001", "field": "skills", "text": "熟练使用 Python"}])
        self.assertIn("copied from the source document", payload["_warnings"][0])

    def test_drops_non_empty_items_without_evidence_text(self) -> None:
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
            source_text="张三，算法工程师，熟练使用 Python，目标大模型算法工程师。",
        )

        self.assertEqual([item["name"] for item in normalized["skills"]], ["Python"])
        self.assertEqual(normalized["evidence"], [{"id": "ev_001", "field": "skills", "text": "熟练使用 Python"}])
        self.assertIn("missing evidence_text", normalized["_warnings"][0])

    def test_fails_when_no_evidence_backed_items_remain(self) -> None:
        payload = _resume_payload()
        payload["skills"][0].pop("evidence_text")

        with self.assertRaisesRegex(ProfileSchemaError, "no evidence-backed list items remained"):
            normalize_profile_payload(
                payload,
                DocumentType.RESUME,
                source_text="张三，算法工程师，熟练使用 Python，目标大模型算法工程师。",
            )


if __name__ == "__main__":
    unittest.main()
