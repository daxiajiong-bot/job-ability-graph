from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from trend_discovery.io_utils import sha256_text
from trend_discovery.schemas import Evidence, ExternalDocument
from trend_discovery.warehouse import Warehouse


duckdb = pytest.importorskip("duckdb")


def _document(text: str = "负责大模型应用开发。", *, raw_hash: str | None = None) -> ExternalDocument:
    return ExternalDocument(
        document_id="doc:test",
        source_type="job",
        source_name="测试招聘源",
        title="大模型应用工程师",
        text=text,
        raw_sha256=raw_hash or sha256_text(text),
        parser_version="test-parser-v1",
        company="测试公司",
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        collected_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        metadata={"source_id": "test"},
    )


def _evidence(document: ExternalDocument, evidence_id: str = "ev:test") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        document_id=document.document_id,
        source_type=document.source_type,
        text=document.text,
        text_sha256=sha256_text(document.text),
        char_start=0,
        char_end=len(document.text),
        section="岗位描述",
    )


def test_upsert_load_export_and_duckdb_summary_tables(tmp_path: Path) -> None:
    warehouse = Warehouse(tmp_path / "warehouse")
    document = _document()
    evidence = _evidence(document)
    summary = {
        "run_id": "run:test",
        "status": "completed",
        "started_at": "2026-07-02T00:00:00+00:00",
        "completed_at": "2026-07-02T00:00:01+00:00",
        "manifest_sha256": "abc",
        "source_summaries": [
            {
                "source_id": "test",
                "source_name": "测试招聘源",
                "source_type": "job",
                "status": "completed",
                "documents": 1,
                "evidence_chunks": 1,
            }
        ],
    }

    result = warehouse.upsert([document], [evidence], run_summary=summary)
    assert result == {
        "documents_inserted": 1,
        "documents_updated": 0,
        "documents_unchanged": 0,
        "documents_total": 1,
        "evidence_inserted": 1,
        "evidence_updated": 0,
        "evidence_unchanged": 0,
        "evidence_deleted": 0,
        "evidence_total": 1,
    }
    assert warehouse.load("documents") == [document]
    assert warehouse.load("evidence") == [evidence]
    assert warehouse.load("runs")[0]["warehouse"]["documents_total"] == 1
    assert warehouse.documents_parquet.exists()
    assert warehouse.evidence_parquet.exists()

    connection = duckdb.connect(str(warehouse.database_path), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM external_documents").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM ingest_runs").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM source_runs").fetchone()[0] == 1
    finally:
        connection.close()

    exported = warehouse.export(tmp_path / "handoff")
    assert exported["external_documents"]["records"] == 1
    assert (tmp_path / "handoff" / "external_documents.jsonl").is_file()
    assert (tmp_path / "handoff" / "evidence.jsonl").is_file()


def test_update_replaces_stale_evidence_and_upsert_is_idempotent(tmp_path: Path) -> None:
    warehouse = Warehouse(tmp_path / "warehouse")
    original = _document("旧的岗位描述。")
    warehouse.upsert([original], [_evidence(original, "ev:old")])

    updated = _document("新的岗位描述，包含 RAG 和 Agent。")
    updated_evidence = _evidence(updated, "ev:new")
    result = warehouse.upsert([updated], [updated_evidence])
    assert result["documents_updated"] == 1
    assert result["evidence_deleted"] == 1
    assert [item.evidence_id for item in warehouse.load("evidence")] == ["ev:new"]

    again = warehouse.upsert([updated], [updated_evidence])
    assert again["documents_inserted"] == 0
    assert again["documents_unchanged"] == 1
    assert again["evidence_unchanged"] == 1
    assert again["documents_total"] == 1
    assert again["evidence_total"] == 1


def test_dangling_evidence_fails_without_changing_existing_state(tmp_path: Path) -> None:
    warehouse = Warehouse(tmp_path / "warehouse")
    document = _document()
    warehouse.upsert([document], [_evidence(document)])
    dangling = Evidence(
        evidence_id="ev:dangling",
        document_id="doc:missing",
        source_type="job",
        text="无来源证据",
        text_sha256=sha256_text("无来源证据"),
        char_start=0,
        char_end=5,
    )

    with pytest.raises(ValueError, match="unknown documents"):
        warehouse.upsert([], [dangling])
    assert warehouse.load("documents") == [document]
    assert [item.evidence_id for item in warehouse.load("evidence")] == ["ev:test"]
