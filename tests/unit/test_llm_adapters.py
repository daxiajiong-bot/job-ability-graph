from __future__ import annotations

import json
import unittest

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.infrastructure.llm import (
    LLMProfileBuilder,
    LLMSettings,
    LightweightSkillNormalizer,
    OllamaStructuredExtractor,
)


class FakeChatClient:
    def __init__(self, content: str | None = None, exc: Exception | None = None) -> None:
        self.content = content
        self.exc = exc
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        if self.exc is not None:
            raise self.exc
        return self.content or ""


def _settings() -> LLMSettings:
    return LLMSettings(
        backend="ollama",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model="qwen2.5:7b",
        timeout_seconds=60,
        max_input_chars=12000,
    )


def _resume_payload() -> str:
    return json.dumps(
        {
            "document_type": "resume",
            "candidate": {"name": "张三", "target_position": "数据分析师"},
            "education": [{"school": "A大学", "degree": "本科", "major": "统计学", "period": "2020-2024", "evidence_ids": ["ev_001"]}],
            "experience": [{"company": "B公司", "role": "实习生", "period": "2024", "description": "数据清洗", "evidence_ids": ["ev_002"]}],
            "projects": [{"name": "推荐系统", "role": "负责人", "description": "建模", "technologies": ["Pytorch"], "evidence_ids": ["ev_003"]}],
            "skills": [
                {"name": " Pytorch ", "category": "深度学习", "level": "熟练", "evidence_ids": ["ev_003"]},
                {"name": "JS", "category": "编程语言", "level": "了解", "evidence_ids": ["ev_004"]},
                {"name": "ML", "category": "算法", "level": "熟练", "evidence_ids": ["ev_005"]},
            ],
            "capabilities": [{"name": "数据建模", "description": "能完成建模分析", "evidence_ids": ["ev_003"]}],
            "responsibilities": [],
            "requirements": [],
            "evidence": [
                {"id": "ev_001", "field": "education", "text": "A大学统计学本科"},
                {"id": "ev_003", "field": "projects", "text": "推荐系统项目使用 Pytorch 建模"},
                {"id": "ev_004", "field": "skills", "text": "掌握 JS"},
                {"id": "ev_005", "field": "skills", "text": "熟悉 ML"},
            ],
        },
        ensure_ascii=False,
    )


def _jd_payload() -> str:
    return json.dumps(
        {
            "document_type": "jd",
            "candidate": {"name": None, "target_position": None},
            "job": {"title": "数据分析师", "department": "业务分析部", "seniority": "初级"},
            "education": [],
            "experience": [],
            "projects": [],
            "skills": [{"name": "Python", "category": "编程语言", "importance": "required", "evidence_ids": ["ev_001"]}],
            "capabilities": [{"name": "数据分析", "description": "能分析业务指标", "evidence_ids": ["ev_002"]}],
            "responsibilities": [{"text": "负责业务数据分析", "evidence_ids": ["ev_002"]}],
            "requirements": [{"text": "熟悉 Python", "importance": "required", "evidence_ids": ["ev_001"]}],
            "evidence": [
                {"id": "ev_001", "field": "requirements", "text": "要求熟悉 Python"},
                {"id": "ev_002", "field": "responsibilities", "text": "负责业务数据分析"},
            ],
        },
        ensure_ascii=False,
    )


class LLMAdapterTest(unittest.TestCase):
    def test_resume_extraction_normalization_and_profile_building(self) -> None:
        document = SourceDocument.create(
            DocumentType.RESUME,
            "张三，目标数据分析师。推荐系统项目使用 Pytorch 建模，掌握 JS，熟悉 ML。",
            {"source_system": "unit-test"},
            {},
        )
        extractor = OllamaStructuredExtractor(_settings(), FakeChatClient(_resume_payload()))
        extraction = extractor.extract(document)
        normalization = LightweightSkillNormalizer().normalize(extraction)
        profile = LLMProfileBuilder().build(ProfileType.CANDIDATE, document, extraction, normalization)

        self.assertEqual(extraction["state"], "available")
        self.assertEqual(extraction["implementation"], "ollama")
        self.assertEqual(normalization["state"], "available")
        self.assertEqual([skill["name"] for skill in normalization["skills"]], ["PyTorch", "JavaScript", "机器学习"])
        self.assertEqual(profile["state"], "available")
        self.assertEqual(profile["implementation"], "llm_profile_builder")
        self.assertEqual(profile["attributes"]["target_position"], "数据分析师")
        self.assertEqual(profile["evidence"][0]["id"], "ev_001")

    def test_jd_profile_includes_requirements_and_responsibilities(self) -> None:
        document = SourceDocument.create(
            DocumentType.JD,
            "数据分析师，要求熟悉 Python，负责业务数据分析。",
            {"source_system": "unit-test"},
            {},
        )
        extraction = OllamaStructuredExtractor(_settings(), FakeChatClient(_jd_payload())).extract(document)
        normalization = LightweightSkillNormalizer().normalize(extraction)
        profile = LLMProfileBuilder().build(ProfileType.JOB, document, extraction, normalization)

        self.assertEqual(profile["state"], "available")
        self.assertEqual(profile["attributes"]["job_title"], "数据分析师")
        self.assertEqual(profile["attributes"]["requirements"][0]["importance"], "required")
        self.assertEqual(profile["attributes"]["responsibilities"][0]["text"], "负责业务数据分析")

    def test_connection_failure_falls_back_to_mock_profile(self) -> None:
        document = SourceDocument.create(DocumentType.RESUME, "简历文本", {"source_system": "unit-test"}, {})
        extraction = OllamaStructuredExtractor(_settings(), FakeChatClient(exc=RuntimeError("connection refused"))).extract(
            document
        )
        normalization = LightweightSkillNormalizer().normalize(extraction)
        profile = LLMProfileBuilder().build(ProfileType.CANDIDATE, document, extraction, normalization)

        self.assertEqual(extraction["state"], "not_implemented")
        self.assertEqual(extraction["implementation"], "mock")
        self.assertIn("connection refused", extraction["warnings"][0])
        self.assertEqual(profile["state"], "not_implemented")
        self.assertEqual(profile["implementation"], "mock")
        self.assertEqual(profile["attributes"]["skills"], [])
        self.assertGreaterEqual(len(profile["warnings"]), 1)

    def test_markdown_or_missing_schema_falls_back(self) -> None:
        document = SourceDocument.create(DocumentType.RESUME, "简历文本", {"source_system": "unit-test"}, {})

        markdown_extraction = OllamaStructuredExtractor(
            _settings(),
            FakeChatClient("```json\n{\"document_type\":\"resume\"}\n```"),
        ).extract(document)
        missing_key_extraction = OllamaStructuredExtractor(
            _settings(),
            FakeChatClient('{"document_type":"resume","candidate":{},"skills":[],"evidence":[]}'),
        ).extract(document)

        self.assertEqual(markdown_extraction["state"], "not_implemented")
        self.assertIn("Markdown", markdown_extraction["warnings"][0])
        self.assertEqual(missing_key_extraction["state"], "not_implemented")
        self.assertIn("missing required keys", missing_key_extraction["warnings"][0])


if __name__ == "__main__":
    unittest.main()
