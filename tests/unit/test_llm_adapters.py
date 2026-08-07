from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from backend.app.domain.entities import DocumentType, ProfileType, SourceDocument
from backend.app.infrastructure.llm import (
    LLMProfileBuilder,
    LLMMatcher,
    LLMSettings,
    LightweightSkillNormalizer,
    OllamaStructuredExtractor,
)
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION


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
            "schema_version": PROFILE_SCHEMA_VERSION,
            "document_type": "resume",
            "candidate": {"name": "张三", "current_title": "数据分析师", "years_of_experience": 4, "location": None},
            "career_intent": {"target_position": "数据分析师", "target_industry": None, "target_location": None},
            "education": [{"school": "A大学", "degree": "本科", "major": "统计学", "period": "2020-2024", "evidence_text": "A大学统计学本科"}],
            "work_experience": [{"company": "B公司", "role": "实习生", "industry": "", "period": "2024", "description": "数据清洗", "evidence_text": "B公司实习生负责数据清洗"}],
            "project_experience": [{"name": "推荐系统", "role": "负责人", "description": "建模", "technologies": ["Pytorch"], "outcomes": [], "evidence_text": "推荐系统项目使用 Pytorch 建模"}],
            "skills": [
                {"name": " Pytorch ", "raw_name": "Pytorch", "category": "framework", "lskt_label": "S", "level": "proficient", "years": None, "evidence_text": "推荐系统项目使用 Pytorch 建模"},
                {"name": "JS", "raw_name": "JS", "category": "programming_language", "lskt_label": "S", "level": "working", "years": None, "evidence_text": "掌握 JS"},
                {"name": "ML", "raw_name": "ML", "category": "algorithm", "lskt_label": "K", "level": "proficient", "years": None, "evidence_text": "熟悉 ML"},
            ],
            "capabilities": [{"name": "数据建模", "description": "能完成建模分析", "level": "proficient", "evidence_text": "能完成建模分析"}],
            "certificates": [],
            "languages": [],
            "achievements": [],
        },
        ensure_ascii=False,
    )


def _jd_payload() -> str:
    return json.dumps(
        {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "document_type": "jd",
            "job": {"title": "数据分析师", "department": "业务分析部", "seniority": "初级"},
            "company": {"name": "某科技公司", "industry": "软件/IT服务", "location": "深圳"},
            "employment": {"employment_type": "full_time", "salary_min": None, "salary_max": None, "published_at": "2026-06-18"},
            "skills": [{"name": "Python", "raw_name": "Python", "category": "programming_language", "lskt_label": "S", "importance": "required", "evidence_text": "要求熟悉 Python"}],
            "capabilities": [{"name": "数据分析", "description": "能分析业务指标", "importance": "required", "evidence_text": "能分析业务指标"}],
            "responsibilities": [{"text": "负责业务数据分析", "evidence_text": "负责业务数据分析"}],
            "requirements": [{"text": "要求熟悉 Python", "requirement_type": "skill", "importance": "required", "evidence_text": "要求熟悉 Python"}],
            "application_scenarios": [{"name": "经营指标监控", "description": "经营指标监控", "evidence_text": "经营指标监控"}],
            "evaluation_signals": [{"name": "BI 看板", "description": "熟悉 BI 看板", "evidence_text": "熟悉 BI 看板"}],
        },
        ensure_ascii=False,
    )


class LLMAdapterTest(unittest.TestCase):
    def test_matcher_falls_back_to_local_scoring_when_llm_times_out(self) -> None:
        candidate = SimpleNamespace(
            attributes={
                "skills": [{"name": "Python"}, {"name": "React"}],
                "projects": [{"name": "demo"}],
            }
        )
        job = SimpleNamespace(
            attributes={
                "skills": [{"name": "Python"}, {"name": "SQL"}],
                "requirements": [],
            }
        )
        matcher = LLMMatcher(_settings(), FakeChatClient(exc=TimeoutError("timed out")))

        result = matcher.assess(candidate, job, {})

        self.assertEqual(result["state"], "available")
        self.assertEqual(result["implementation"], "deterministic_matcher_fallback")
        self.assertIsInstance(result["score"], int)
        self.assertEqual(result["details"]["skill_score"], 50)
        self.assertIn("timed out", result["warnings"][0])

    def test_matcher_falls_back_when_llm_result_shape_is_invalid(self) -> None:
        candidate = SimpleNamespace(attributes={"skills": [{"name": "Python"}]})
        job = SimpleNamespace(attributes={"skills": [{"name": "Python"}]})
        matcher = LLMMatcher(
            _settings(),
            FakeChatClient('{"score": null, "decision": "match", "strengths": null}'),
        )

        result = matcher.assess(candidate, job, {})

        self.assertEqual(result["state"], "available")
        self.assertEqual(result["implementation"], "deterministic_matcher_fallback")

    def test_resume_extraction_normalization_and_profile_building(self) -> None:
        document = SourceDocument.create(
            DocumentType.RESUME,
            "张三，现任数据分析师，4年经验，目标岗位数据分析师。A大学统计学本科。B公司实习生负责数据清洗。推荐系统项目使用 Pytorch 建模，掌握 JS，熟悉 ML，能完成建模分析。",
            {"source_system": "unit-test"},
            {},
        )
        extractor = OllamaStructuredExtractor(_settings(), FakeChatClient(_resume_payload()))
        extraction = extractor.extract(document)
        normalization = LightweightSkillNormalizer().normalize(extraction)
        profile = LLMProfileBuilder().build(ProfileType.CANDIDATE, document, extraction, normalization)

        self.assertEqual(extraction["state"], "available")
        self.assertEqual(extraction["implementation"], "ollama")
        self.assertEqual(extraction["schema"], PROFILE_SCHEMA_VERSION)
        self.assertEqual(normalization["state"], "available")
        self.assertEqual([skill["name"] for skill in normalization["skills"]], ["Pytorch", "JS", "machine learning"])
        self.assertEqual([skill["linking_status"] for skill in normalization["skills"]], ["unmapped", "unmapped", "linked"])
        self.assertEqual(profile["state"], "available")
        self.assertEqual(profile["implementation"], "llm_profile_builder")
        self.assertEqual(profile["attributes"]["target_position"], "数据分析师")
        self.assertEqual(profile["attributes"]["resume_profile"]["schema_version"], PROFILE_SCHEMA_VERSION)
        self.assertEqual(profile["attributes"]["resume_profile"]["skills"][1]["name"], "JS")
        self.assertEqual(profile["attributes"]["resume_profile"]["skills"][1]["evidence_ids"], ["ev_004"])
        self.assertEqual(profile["evidence"][0]["id"], "ev_001")
        self.assertEqual(profile["evidence"][0]["text"], "A大学统计学本科")

    def test_jd_profile_includes_requirements_and_responsibilities(self) -> None:
        document = SourceDocument.create(
            DocumentType.JD,
            "数据分析师，业务分析部，初级。公司：某科技公司，软件/IT服务，深圳。全职，2026-06-18发布。要求熟悉 Python。负责业务数据分析。能分析业务指标。应用场景：经营指标监控。加分项：熟悉 BI 看板。",
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
        self.assertEqual(profile["attributes"]["requirements"][0]["evidence_ids"], ["ev_002"])
        self.assertEqual(profile["attributes"]["jd_profile"]["application_scenarios"][0]["name"], "经营指标监控")
        self.assertEqual(profile["evidence"][0]["text"], "负责业务数据分析")

    def test_connection_failure_falls_back_to_heuristic_profile(self) -> None:
        document = SourceDocument.create(DocumentType.RESUME, "简历文本", {"source_system": "unit-test"}, {})
        extraction = OllamaStructuredExtractor(_settings(), FakeChatClient(exc=RuntimeError("connection refused"))).extract(
            document
        )
        normalization = LightweightSkillNormalizer().normalize(extraction)
        profile = LLMProfileBuilder().build(ProfileType.CANDIDATE, document, extraction, normalization)

        self.assertEqual(extraction["state"], "not_implemented")
        self.assertEqual(extraction["implementation"], "mock")
        self.assertIn("connection refused", extraction["warnings"][0])
        self.assertEqual(profile["state"], "available")
        self.assertEqual(profile["implementation"], "heuristic_profile_builder")
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
            FakeChatClient('{"schema_version":"profile-extraction/v2","document_type":"resume","candidate":{},"skills":[]}'),
        ).extract(document)

        markdown_profile = LLMProfileBuilder().build(
            ProfileType.CANDIDATE,
            document,
            markdown_extraction,
            LightweightSkillNormalizer().normalize(markdown_extraction),
        )
        missing_key_profile = LLMProfileBuilder().build(
            ProfileType.CANDIDATE,
            document,
            missing_key_extraction,
            {"state": "not_implemented", "skills": []},
        )

        self.assertEqual(markdown_extraction["state"], "not_implemented")
        self.assertIn("Markdown", markdown_extraction["warnings"][0])
        self.assertIn("```json", markdown_extraction["raw_model_output"])
        self.assertIn("Markdown", markdown_extraction["validation_error"])
        self.assertEqual(markdown_profile["state"], "available")
        self.assertEqual(markdown_profile["implementation"], "heuristic_profile_builder")
        self.assertEqual(missing_key_extraction["state"], "available")
        self.assertIn("missing schema fields auto-filled", missing_key_extraction["warnings"][0])
        self.assertEqual(missing_key_profile["state"], "available")
        self.assertEqual(missing_key_profile["implementation"], "llm_profile_builder")


if __name__ == "__main__":
    unittest.main()
