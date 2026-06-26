from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.infrastructure.wiring import build_container


class FakeOcr:
    def extract_text(self, **kwargs):
        return {
            "state": "available",
            "implementation": "fake-ocr",
            "lang": kwargs["lang"],
            "text": "private OCR resume text",
            "page_count": 1,
            "line_count": 1,
            "average_confidence": 0.98,
            "pages": [{"index": 0, "lines": [{"index": 0, "text": "private OCR resume text", "confidence": 0.98}]}],
            "warnings": [],
        }


class FakeChatClient:
    def chat(self, messages):
        return json.dumps(
            {
                "document_type": "resume",
                "candidate": {"name": "张三", "target_position": "数据分析师"},
                "education": [],
                "experience": [],
                "projects": [],
                "skills": [{"name": "JS", "category": "编程语言", "level": "了解", "evidence_ids": ["ev_001"]}],
                "capabilities": [{"name": "数据分析", "description": "能分析业务数据", "evidence_ids": ["ev_002"]}],
                "responsibilities": [],
                "requirements": [],
                "evidence": [
                    {"id": "ev_001", "field": "skills", "text": "掌握 JS"},
                    {"id": "ev_002", "field": "capabilities", "text": "能分析业务数据"},
                ],
            },
            ensure_ascii=False,
        )


class V3ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        app.state.container = build_container(ocr=FakeOcr())
        self.client = TestClient(app)

    def _document(self, document_type: str, text: str, client: TestClient | None = None) -> str:
        api_client = client or self.client
        response = api_client.post(
            "/api/v1/documents",
            json={"document_type": document_type, "text": text, "source": {"source_system": "contract-test"}},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["meta"]["api_version"], "v1")
        self.assertNotIn(text, str(body))
        return body["data"]["document"]["id"]

    def test_v3_resource_lifecycle_and_mock_boundaries(self) -> None:
        resume_id = self._document("resume", "private resume text")
        jd_id = self._document("jd", "private JD text")
        policy_id = self._document("policy", "policy source text")
        self._document("industry_report", "industry source text")
        self._document("market_data", "market source text")

        candidate = self.client.post("/api/v1/candidate-profiles", json={"document_id": resume_id}).json()["data"]["profile"]
        job = self.client.post("/api/v1/job-profiles", json={"document_id": jd_id}).json()["data"]["profile"]
        self.assertEqual(candidate["state"], "not_implemented")
        self.assertEqual(candidate["attributes"]["skills"], [])
        self.assertEqual(job["profile_type"], "job")

        retrieval = self.client.post(
            "/api/v1/document-retrievals", json={"query": "evidence", "document_ids": [resume_id, jd_id]}
        ).json()["data"]["retrieval"]
        self.assertEqual(retrieval["evidence"], [])

        graph_response = self.client.post(
            "/api/v1/knowledge-graphs",
            json={"candidate_profile_ids": [candidate["id"]], "job_profile_ids": [job["id"]]},
        )
        self.assertEqual(graph_response.status_code, 201)
        graph = graph_response.json()["data"]["knowledge_graph"]
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])

        graph_retrieval = self.client.post(
            f"/api/v1/graph-retrievals?graph_id={graph['id']}", json={"query": "path"}
        ).json()["data"]["retrieval"]
        self.assertEqual(graph_retrieval["paths"], [])

        discovery = self.client.post(
            "/api/v1/position-discoveries", json={"document_ids": [policy_id]}
        ).json()["data"]["discovery"]
        self.assertEqual(discovery["candidate_positions"], [])

        comparison = self.client.post(
            "/api/v1/position-deltas",
            json={"baseline_job_profile_id": job["id"], "current_job_profile_id": job["id"]},
        ).json()["data"]["delta"]
        self.assertEqual(comparison["changed"], [])

        match_response = self.client.post(
            "/api/v1/matches", json={"candidate_profile_id": candidate["id"], "job_profile_id": job["id"]}
        )
        self.assertEqual(match_response.status_code, 201)
        match = match_response.json()["data"]["match"]
        self.assertIsNone(match["score"])
        self.assertEqual(match["decision"], "not_evaluated")

        report = self.client.post("/api/v1/reports", json={"match_id": match["id"]}).json()["data"]["report"]
        self.assertEqual(report["sections"], [])
        self.assertEqual(report["state"], "not_implemented")

    def test_errors_are_enveloped_and_legacy_routes_are_gone(self) -> None:
        validation = self.client.post("/api/v1/documents", json={"document_type": "resume", "text": "   "})
        self.assertEqual(validation.status_code, 422)
        self.assertEqual(validation.json()["error"]["code"], "validation_error")

        missing = self.client.get("/api/v1/documents/does-not-exist")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "resource_not_found")

        legacy = self.client.get("/samples")
        self.assertEqual(legacy.status_code, 404)
        self.assertEqual(legacy.json()["error"]["code"], "http_404")

    def test_ocr_upload_creates_document_without_echoing_text(self) -> None:
        response = self.client.post(
            "/api/v1/documents/ocr",
            data={"document_type": "resume", "lang": "ch", "metadata_json": '{"scan":"campus-fair"}'},
            files={"file": ("resume.png", b"fake image bytes", "image/png")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertNotIn("private OCR resume text", str(body))

        document = body["data"]["document"]
        self.assertEqual(document["document_type"], "resume")
        self.assertEqual(document["char_count"], len("private OCR resume text"))
        self.assertEqual(document["metadata"]["scan"], "campus-fair")
        self.assertEqual(document["metadata"]["ocr"]["implementation"], "fake-ocr")
        self.assertEqual(body["data"]["ocr"]["line_count"], 1)

    def test_ollama_mode_profiles_and_capabilities_are_available(self) -> None:
        with patch.dict("os.environ", {"LLM_BACKEND": "ollama"}, clear=False):
            app.state.container = build_container(ocr=FakeOcr(), llm_chat_client=FakeChatClient())
            client = TestClient(app)

            resume_id = self._document("resume", "张三掌握 JS，能分析业务数据。", client)
            profile_response = client.post("/api/v1/candidate-profiles", json={"document_id": resume_id})
            self.assertEqual(profile_response.status_code, 201, profile_response.text)
            profile = profile_response.json()["data"]["profile"]
            self.assertEqual(profile["state"], "available")
            self.assertEqual(profile["implementation"], "llm_profile_builder")
            self.assertEqual(profile["attributes"]["skills"][0]["name"], "JavaScript")

            capabilities = client.get("/api/v1/capabilities").json()["data"]["capabilities"]
            by_name = {item["name"]: item for item in capabilities}
            self.assertEqual(by_name["structured_extraction"]["implementation"], "ollama")
            self.assertEqual(by_name["structured_extraction"]["state"], "available")
            self.assertEqual(by_name["profile_builder"]["implementation"], "llm_profile_builder")
