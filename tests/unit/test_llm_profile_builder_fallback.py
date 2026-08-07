from __future__ import annotations

import unittest

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.infrastructure.llm.adapters import LLMProfileBuilder


def _failed_extraction() -> dict:
    return {
        "state": "not_implemented",
        "reason": "local LLM request failed: timed out",
        "warnings": ["local LLM request failed: timed out"],
    }


class LLMProfileBuilderFallbackTest(unittest.TestCase):
    def test_resume_fallback_builds_available_profile(self) -> None:
        text = (
            "\u59d3\u540d\uff1a\u674e\u56db\n"
            "\u6c42\u804c\u5c97\u4f4d\uff1aAI\u5927\u6a21\u578b\u5e94\u7528\u5de5\u7a0b\u5e08\n"
            "\u719f\u6089 Python\u3001Prompt\u3001RAG\u3001\u77e5\u8bc6\u5e93\u3001\u5927\u6a21\u578b\u5e94\u7528\u3002"
        )
        doc = SourceDocument.create(DocumentType.RESUME, text, {"source_system": "manual"}, {})

        result = LLMProfileBuilder().build(
            ProfileType.CANDIDATE,
            doc,
            _failed_extraction(),
            {"state": "not_implemented", "skills": []},
        )

        self.assertEqual(result["state"], "available")
        self.assertEqual(result["implementation"], "heuristic_profile_builder")
        self.assertEqual(result["attributes"]["candidate"]["name"], "\u674e\u56db")
        self.assertEqual(
            result["attributes"]["target_position"],
            "AI\u5927\u6a21\u578b\u5e94\u7528\u5de5\u7a0b\u5e08",
        )
        self.assertIn("Prompt", [skill["name"] for skill in result["attributes"]["skills"]])

    def test_jd_fallback_builds_available_profile(self) -> None:
        text = (
            "\u5c97\u4f4d\u540d\u79f0\uff1aAI\u5927\u6a21\u578b\u5e94\u7528\u5de5\u7a0b\u5e08\n"
            "\u6240\u5c5e\u90e8\u95e8\uff1a\u4eba\u5de5\u667a\u80fd\u4ea7\u54c1\u7814\u53d1\u90e8\n"
            "\u5c97\u4f4d\u804c\u8d23\n"
            "- \u8d1f\u8d23 Prompt \u4f18\u5316\u548c\u5927\u6a21\u578b\u5e94\u7528\u5f00\u53d1\u3002\n"
            "\u4efb\u804c\u8981\u6c42\n"
            "- \u719f\u6089 Python\u3001RAG \u548c\u77e5\u8bc6\u5e93\u642d\u5efa\u3002"
        )
        doc = SourceDocument.create(DocumentType.JD, text, {"source_system": "manual"}, {})

        result = LLMProfileBuilder().build(
            ProfileType.JOB,
            doc,
            _failed_extraction(),
            {"state": "not_implemented", "skills": []},
        )

        self.assertEqual(result["state"], "available")
        self.assertEqual(result["implementation"], "heuristic_profile_builder")
        self.assertEqual(
            result["attributes"]["job"]["title"],
            "AI\u5927\u6a21\u578b\u5e94\u7528\u5de5\u7a0b\u5e08",
        )
        self.assertGreaterEqual(len(result["attributes"]["responsibilities"]), 1)
        self.assertGreaterEqual(len(result["attributes"]["requirements"]), 1)
        self.assertIn("RAG", [skill["name"] for skill in result["attributes"]["skills"]])


if __name__ == "__main__":
    unittest.main()
