from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.data_governance import DataGovernanceService
from backend.app.data_governance.lskt import OllamaLsktDraftExtractor
from backend.app.data_governance.esco import EscoIndex, EscoLinker, build_esco_index
from backend.app.infrastructure.llm.settings import LLMSettings


ESCO_INDEX = Path("data/esco").resolve()


class FakeChatClient:
    def __init__(self, content: str | None = None) -> None:
        self.content = content

    def chat(self, messages):
        if self.content is not None:
            return self.content
        prompt = messages[-1]["content"]
        if "output_schema" in prompt:
            return self._choice(prompt)
        if "queries" in prompt and "span:" in prompt:
            return self._queries(prompt)
        return self._spans(prompt)

    def _spans(self, prompt: str) -> str:
        known = ["Python", "MySQL", "数据分析", "统计学", "操作系统", "数据清洗", "模型训练", "接口对接", "沟通能力", "团队协作"]
        spans = []
        for value in known:
            start = prompt.find(value)
            if start < 0:
                continue
            label = {"统计学": "K", "操作系统": "K", "沟通能力": "T", "团队协作": "T"}.get(value, "S")
            spans.append({"surface": value, "lskt_label": label, "start_char": 0, "end_char": 0, "confidence": 0.9})
        source = prompt.split("原文：", 1)[-1]
        for span in spans:
            start = source.find(span["surface"])
            span["start_char"] = start
            span["end_char"] = start + len(span["surface"])
        return json.dumps({"spans": [span for span in spans if span["start_char"] >= 0]}, ensure_ascii=False)

    def _queries(self, prompt: str) -> str:
        mapping = {
            "Python": ["Python"],
            "MySQL": ["MySQL"],
            "数据分析": ["data analysis"],
            "统计学": ["statistics"],
            "操作系统": ["operating systems"],
            "数据清洗": ["data analysis"],
            "模型训练": ["model training"],
            "接口对接": ["software integration"],
            "沟通能力": ["communication skills"],
            "团队协作": ["teamwork"],
            "英语六级": ["English"],
        }
        for span, queries in mapping.items():
            if f"span: {span}" in prompt:
                return json.dumps({"queries": queries}, ensure_ascii=False)
        return json.dumps({"queries": []}, ensure_ascii=False)

    def _choice(self, prompt: str) -> str:
        payload = json.loads(prompt)
        candidates = payload.get("candidates", [])
        expected_label = payload.get("lskt_label")
        matched = next((candidate for candidate in candidates if candidate.get("lskt_label") == expected_label), None)
        uri = (matched or candidates[0])["esco_uri"] if candidates else ""
        return json.dumps({"esco_uri": uri, "confidence": 0.9}, ensure_ascii=False)


def _settings() -> LLMSettings:
    return LLMSettings(
        backend="ollama",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model="qwen2.5:7b",
        timeout_seconds=60,
        max_input_chars=12000,
    )


class DataGovernanceServiceTest(unittest.TestCase):
    def test_register_deduplicate_version_process_and_rag(self) -> None:
        with TemporaryDirectory() as root:
            service = DataGovernanceService(root=root, esco_index_root=ESCO_INDEX, llm_chat_client=FakeChatClient())

            first = service.register_upload(
                document_type="jd",
                content="岗位要求：熟悉 Python、MySQL，负责数据分析。".encode("utf-8"),
                file_name="jd.txt",
                mime_type="text/plain",
                source={"source_system": "unit", "external_id": "jd-1"},
                metadata={"batch": "unit"},
            )["document"]
            duplicate = service.register_upload(
                document_type="jd",
                content="岗位要求：熟悉 Python、MySQL，负责数据分析。".encode("utf-8"),
                file_name="jd-copy.txt",
                mime_type="text/plain",
                source={"source_system": "unit", "external_id": "jd-copy"},
                metadata={},
            )["document"]
            changed = service.register_upload(
                document_type="jd",
                content="岗位要求：熟悉 Python、Redis。".encode("utf-8"),
                file_name="jd-v2.txt",
                mime_type="text/plain",
                source={"source_system": "unit", "external_id": "jd-1"},
                metadata={},
            )["document"]

            self.assertEqual(first["version"], 1)
            self.assertEqual(duplicate["status"], "duplicate")
            self.assertEqual(duplicate["duplicate_of"], f"{first['doc_id']}:v1")
            self.assertEqual(changed["doc_id"], first["doc_id"])
            self.assertEqual(changed["version"], 2)

            processed = service.process_document(first["doc_id"], 1)
            self.assertEqual(processed["status"], "processed")
            self.assertGreaterEqual(processed["counts"]["chunks"], 1)
            self.assertGreaterEqual(processed["counts"]["entity_candidates"], 2)
            self.assertEqual(processed["quality"]["doc_id"], first["doc_id"])
            for artifact_name in (
                "quality",
                "parsed",
                "chunks_staging",
                "entity_candidates",
                "relation_candidates",
                "entities",
                "relations",
                "rag_chunks",
            ):
                path = Path(processed["artifacts"][artifact_name])
                if path.suffix == ".jsonl":
                    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    self.assertTrue(rows)
                    self.assertTrue(all(row["doc_id"] == first["doc_id"] for row in rows))
                else:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["doc_id"], first["doc_id"])

            graph = json.loads(Path(processed["artifacts"]["graph"]).read_text(encoding="utf-8"))
            self.assertEqual(graph["doc_id"], first["doc_id"])
            self.assertTrue(all(node["doc_id"] == first["doc_id"] for node in graph["nodes"]))
            self.assertTrue(all(edge["doc_id"] == first["doc_id"] for edge in graph["edges"]))
            semantic_edges = [edge for edge in graph["edges"] if edge["relation_type"] == "REQUIRES_SKILL"]
            self.assertTrue(semantic_edges)
            for edge in semantic_edges:
                self.assertEqual(edge["doc_id"], first["doc_id"])
                self.assertTrue(edge["evidence_ids"])
                self.assertIn("quote", edge["evidence"][0])
                self.assertEqual(edge["evidence"][0]["doc_id"], first["doc_id"])
                self.assertTrue(edge["evidence"][0]["chunk_id"].startswith(first["doc_id"]))

            answer = service.answer("Python MySQL", [first["doc_id"]], 3)
            self.assertTrue(answer["citations"])
            citation = answer["citations"][0]
            self.assertEqual(citation["doc_id"], first["doc_id"])
            self.assertIn("chunk_id", citation)
            self.assertIn("Python", citation["quote"])

            lineage = service.lineage(first["doc_id"], 1)
            self.assertEqual(lineage["raw"]["content_hash"], first["content_hash"])
            self.assertTrue(lineage["invariants"]["chunks_trace_to_raw_path"])

    def test_lskt_spans_are_classified_and_bound_to_evidence(self) -> None:
        with TemporaryDirectory() as root:
            service = DataGovernanceService(root=root, esco_index_root=ESCO_INDEX, llm_chat_client=FakeChatClient())
            source_text = "岗位要求：掌握统计学和操作系统，负责数据清洗、模型训练和接口对接；具备沟通能力和团队协作，英语六级优先。"
            document = service.register_upload(
                document_type="jd",
                content=source_text.encode("utf-8"),
                file_name="jd-lskt.txt",
                mime_type="text/plain",
                source={"source_system": "unit", "external_id": "jd-lskt"},
                metadata={},
            )["document"]

            processed = service.process_document(document["doc_id"], 1)
            parsed = json.loads(Path(processed["artifacts"]["parsed"]).read_text(encoding="utf-8"))
            entities = [
                json.loads(line)
                for line in Path(processed["artifacts"]["entities"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            labels = {entity["lskt_label"] for entity in entities}

            self.assertEqual(labels, {"K", "S", "T", "L"})
            for entity in entities:
                self.assertIn(entity["surface"], entity["evidence"]["quote"])
                self.assertEqual(parsed["text"][entity["start_char"] : entity["end_char"]], entity["surface"])
                self.assertIn(entity["normalization_status"], {"esco_linked", "unmapped"})
                if entity["linking_status"] == "linked":
                    self.assertTrue(entity["esco_uri"])
                    self.assertTrue(entity["esco_preferred_label"])

            graph = json.loads(Path(processed["artifacts"]["graph"]).read_text(encoding="utf-8"))
            skill_nodes = [node for node in graph["nodes"] if node["label"] == "Skill"]
            self.assertTrue(any(node["properties"].get("lskt_label") == "K" for node in skill_nodes))
            self.assertTrue(any(edge["properties"].get("lskt_label") == "S" for edge in graph["edges"]))

            rag_rows = [
                json.loads(line)
                for line in Path(processed["artifacts"]["rag_chunks"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(any("competency_spans" in row and row["competency_spans"] for row in rag_rows))

    def test_ollama_draft_discards_spans_not_present_in_source_text(self) -> None:
        extractor = OllamaLsktDraftExtractor(
            chat_client=FakeChatClient(
                json.dumps(
                    {
                        "spans": [
                            {"surface": "数据分析", "lskt_label": "S", "start_char": 2, "end_char": 6, "confidence": 0.9},
                            {"surface": "不存在技能", "lskt_label": "S", "start_char": 0, "end_char": 5, "confidence": 0.9},
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            settings=_settings(),
        )

        candidates = extractor.extract("负责数据分析。")

        self.assertEqual([candidate.surface for candidate in candidates], ["数据分析"])

    def test_ollama_draft_splits_compound_context_spans(self) -> None:
        extractor = OllamaLsktDraftExtractor(
            chat_client=FakeChatClient(
                json.dumps(
                    {
                        "spans": [
                            {
                                "surface": "掌握 Python 和 MySQL",
                                "lskt_label": "S",
                                "start_char": 5,
                                "end_char": 23,
                                "confidence": 0.9,
                            },
                            {
                                "surface": "英语六级优先",
                                "lskt_label": "L",
                                "start_char": 24,
                                "end_char": 30,
                                "confidence": 0.9,
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            settings=_settings(),
        )

        text = "岗位要求：掌握 Python 和 MySQL，英语六级优先。"
        candidates = extractor.extract(text)

        self.assertEqual([candidate.surface for candidate in candidates], ["Python", "MySQL", "英语六级"])
        for candidate in candidates:
            self.assertEqual(text[candidate.start_char : candidate.end_char], candidate.surface)

    def test_ollama_draft_accepts_json_wrapped_by_model_text(self) -> None:
        wrapped = (
            '润色后：{"spans":[]}</think>\n'
            '{"spans":[{"surface":"Python","lskt_label":"S","start_char":0,"end_char":1,"confidence":0.9}]}'
        )
        extractor = OllamaLsktDraftExtractor(chat_client=FakeChatClient(wrapped), settings=_settings())

        candidates = extractor.extract("岗位要求：掌握 Python。")

        self.assertEqual([candidate.surface for candidate in candidates], ["Python"])
        self.assertEqual(candidates[0].start_char, 8)

    def test_esco_linker_rejects_uri_outside_candidate_whitelist(self) -> None:
        class InvalidUriChatClient:
            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"queries": ["model training"]}, ensure_ascii=False)
                return json.dumps({"esco_uri": "http://example.invalid/esco/skill/fake", "confidence": 0.99})

        linker = EscoLinker(EscoIndex.from_root(ESCO_INDEX), chat_client=InvalidUriChatClient())

        result = linker.link("模型训练", "负责模型训练", "S")

        self.assertEqual(result.linking_status, "unmapped")
        self.assertIsNone(result.concept)

    def test_register_path_copies_raw_without_mutating_source(self) -> None:
        with TemporaryDirectory() as root:
            source_path = Path(root) / "source_resume.txt"
            source_text = "候选人掌握 Python、Linux 和 Git。"
            source_path.write_text(source_text, encoding="utf-8")

            service = DataGovernanceService(root=Path(root) / "governed", esco_index_root=ESCO_INDEX, llm_chat_client=FakeChatClient())
            registered = service.register_path(
                document_type="resume",
                path=str(source_path),
                source={"source_system": "unit", "external_id": "resume-1"},
                metadata={},
            )["document"]

            self.assertEqual(source_path.read_text(encoding="utf-8"), source_text)
            self.assertNotEqual(str(source_path), registered["raw_path"])
            self.assertTrue(Path(registered["raw_path"]).exists())

    def test_build_esco_index_from_minimal_csv_fixture(self) -> None:
        with TemporaryDirectory() as root:
            source = Path(root) / "official"
            output = Path(root) / "esco"
            source.mkdir()
            (source / "skills_en.csv").write_text(
                "conceptUri,preferredLabel,altLabels,description,scopeNote,skillType,reuseLevel\n"
                "http://data.europa.eu/esco/skill/x,example skill,example alias,Example description,,knowledge,cross-sector\n",
                encoding="utf-8",
            )

            manifest = build_esco_index(source, output, version="v-test")
            rows = [
                json.loads(line)
                for line in (output / "index" / "concepts.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(manifest["concept_count"], 1)
            self.assertEqual(rows[0]["esco_uri"], "http://data.europa.eu/esco/skill/x")
            self.assertEqual(rows[0]["lskt_label"], "K")


if __name__ == "__main__":
    unittest.main()
