from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from trend_discovery.ingest import ingest_manifest, load_source_manifest
from trend_discovery.parsers import build_evidence, parse_source
from trend_discovery.schemas import SourceSpec
from trend_discovery.warehouse import Warehouse


pytest.importorskip("duckdb")


def _config(**overrides: object) -> dict[str, object]:
    parsing: dict[str, object] = {
        "parser_version": "test-parser-v1",
        "chunk_chars": 45,
        "chunk_overlap": 5,
        "min_pdf_text_chars_per_page": 20,
        "request_timeout_seconds": 2,
        "user_agent": "jobtrend-test/1",
        "use_docling": False,
    }
    parsing.update(overrides)
    return {"parsing": parsing}


def _write_manifest(path: Path, sources: list[dict[str, object]]) -> Path:
    path.write_text(
        yaml.safe_dump(
            {"schema_version": "source_manifest_v1", "sources": sources},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_manifest_schema_and_duplicate_source_ids(tmp_path: Path) -> None:
    valid = _write_manifest(
        tmp_path / "sources.yaml",
        [
            {
                "source_id": "jd-csv",
                "source_type": "job",
                "input": "jobs.csv",
                "input_format": "csv",
                "source_name": "企业官网",
            }
        ],
    )
    manifest = load_source_manifest(valid)
    assert manifest.schema_version == "source_manifest_v1"
    assert manifest.sources[0].input == "jobs.csv"

    duplicate = _write_manifest(
        tmp_path / "duplicate.yaml",
        [
            {
                "source_id": "same",
                "source_type": "job",
                "input": "one.txt",
                "source_name": "one",
            },
            {
                "source_id": "same",
                "source_type": "policy",
                "input": "two.txt",
                "source_name": "two",
            },
        ],
    )
    with pytest.raises(ValidationError, match="source_id values must be unique"):
        load_source_manifest(duplicate)


def test_csv_alias_normalization_dates_and_evidence_spans(tmp_path: Path) -> None:
    csv_path = tmp_path / "jobs.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "job_id",
                "job_title",
                "company_name",
                "industry",
                "location",
                "publish_date",
                "scrape_time",
                "jd_text",
                "url",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "job_id": "corp-001",
                "job_title": "大模型应用工程师",
                "company_name": "示例科技",
                "industry": "人工智能",
                "location": "上海",
                "publish_date": "2026-07-01 09:30:00",
                "scrape_time": "2026-07-02 10:45:00",
                "jd_text": "负责 Agent 工作流设计。\n岗位要求：熟悉 Python、RAG 和向量数据库。",
                "url": "https://careers.example/jobs/corp-001",
            }
        )
    manifest_path = _write_manifest(
        tmp_path / "sources.yaml",
        [
            {
                "source_id": "official-jobs",
                "source_type": "job",
                "input": "jobs.csv",
                "input_format": "csv",
                "source_name": "企业官网",
            }
        ],
    )

    result = ingest_manifest(manifest_path, tmp_path / "warehouse", _config())
    assert result["status"] == "completed"
    assert result["warehouse"]["documents_total"] == 1

    warehouse = Warehouse(tmp_path / "warehouse")
    document = warehouse.load("documents")[0]
    assert document.title == "大模型应用工程师"
    assert document.company == "示例科技"
    assert document.region == "上海"
    assert document.published_at == datetime(2026, 7, 1, 9, 30)
    assert document.collected_at == datetime(2026, 7, 2, 10, 45)
    assert document.published_at != document.collected_at

    chunks = warehouse.load("evidence")
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.char_start is not None and chunk.char_end is not None
        assert document.text[chunk.char_start : chunk.char_end] == chunk.text


def test_url_jsonl_fetcher_and_incremental_idempotency(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "sources.yaml",
        [
            {
                "source_id": "remote-jobs",
                "source_type": "job",
                "input": "https://data.example/jobs.jsonl",
                "input_format": "jsonl",
                "source_name": "企业招聘页",
            }
        ],
    )
    calls: list[tuple[str, dict[str, str]]] = []
    body = (
        json.dumps(
            {
                "id": "remote-1",
                "title": "生成式 AI 产品工程师",
                "description": "设计和评估生成式 AI 产品。",
                "company": "远程示例公司",
                "published_at": "2026-08-01T08:00:00+08:00",
                "collected_at": "2026-08-02T08:00:00+08:00",
            },
            ensure_ascii=False,
        )
        + "\n"
    ).encode()

    def fake_fetcher(url: str, **kwargs: object) -> tuple[bytes, str]:
        calls.append((url, dict(kwargs["headers"])))  # type: ignore[arg-type]
        return body, "application/x-ndjson"

    first = ingest_manifest(manifest_path, tmp_path / "warehouse", _config(), fetcher=fake_fetcher)
    second = ingest_manifest(manifest_path, tmp_path / "warehouse", _config(), fetcher=fake_fetcher)

    assert len(calls) == 2
    assert calls[0][1]["User-Agent"] == "jobtrend-test/1"
    assert first["warehouse"]["documents_total"] == 1
    assert second["warehouse"]["documents_total"] == 1
    assert second["warehouse"]["documents_inserted"] == 0
    assert second["warehouse"]["documents_unchanged"] == 1
    assert len(Warehouse(tmp_path / "warehouse").load("evidence")) == 1


def test_url_pdf_magic_bytes_override_incorrect_content_type(tmp_path: Path) -> None:
    """Authoritative download endpoints can label a PDF as an Excel file."""

    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Title": "人工智能训练师国家职业技能标准"})
    payload = io.BytesIO()
    writer.write(payload)

    source = SourceSpec(
        source_id="osta-ai-trainer-standard",
        source_type="occupational_standard",
        input=(
            "https://www.osta.org.cn/api/sys/downloadFile/decrypt"
            "?fileName=artificial-intelligence-trainer"
        ),
        input_format="auto",
        source_name="OSTA",
    )

    def fake_fetcher(url: str, **_: object) -> tuple[bytes, str]:
        assert not url.endswith(".pdf")
        return payload.getvalue(), "application/vnd.ms-excel"

    parsed = parse_source(source, tmp_path, _config(), fetcher=fake_fetcher)[0]

    assert parsed.document.metadata["detected_format"] == "pdf"
    assert parsed.document.metadata["page_count"] == 1
    assert parsed.document.title == "人工智能训练师国家职业技能标准"
    # The fixture is deliberately blank; correct PDF detection still preserves
    # the existing no-OCR policy instead of sending bytes to the HTML parser.
    assert parsed.document.parse_status == "needs_ocr"


def test_url_html_magic_bytes_are_detected_without_bytes_casefold_error(tmp_path: Path) -> None:
    source = SourceSpec(
        source_id="government-policy-page",
        source_type="policy",
        input="https://www.example.gov.cn/article/no-suffix",
        input_format="url",
        source_name="政府网站",
    )

    def fake_fetcher(url: str, **_: object) -> tuple[bytes, str]:
        assert url.endswith("no-suffix")
        return (
            b"<!DOCTYPE HTML><html><head><title>Policy</title></head>"
            b"<body><p>AI policy</p></body></html>",
            "application/octet-stream",
        )

    parsed = parse_source(source, tmp_path, _config(), fetcher=fake_fetcher)[0]

    assert parsed.document.metadata["detected_format"] == "html"
    assert parsed.document.title == "Policy"
    assert parsed.document.text == "AI policy"


def test_html_nested_div_fallback_keeps_government_article_text(tmp_path: Path) -> None:
    body = "人工智能产业政策正文" * 30
    html_path = tmp_path / "government.html"
    html_path.write_text(
        "<html><head><title>政策通知</title></head><body>"
        "<nav>首页 政务公开</nav><div id='UCAP-CONTENT'><div><span>" + body + "</span></div></div>"
        "<footer>版权信息</footer></body></html>",
        encoding="utf-8",
    )
    source = SourceSpec(
        source_id="nested-government-page",
        source_type="policy",
        input=str(html_path),
        input_format="html",
        source_name="政府网站",
    )

    parsed = parse_source(source, tmp_path, _config())[0]

    assert body in parsed.document.text
    assert "政务公开" not in parsed.document.text
    assert "版权信息" not in parsed.document.text


def test_text_html_and_docx_parsers_keep_traceable_segments(tmp_path: Path) -> None:
    text_path = tmp_path / "policy.txt"
    text_path.write_text("人工智能政策\n\n重点任务：\n支持大模型安全治理和人才培养。", encoding="utf-8")
    text_source = SourceSpec(
        source_id="policy-text",
        source_type="policy",
        input=str(text_path),
        input_format="txt",
        source_name="政策发布平台",
    )
    parsed_text = parse_source(text_source, tmp_path, _config())[0]
    assert any(segment.section == "重点任务" for segment in parsed_text.segments)

    pytest.importorskip("bs4")
    html_path = tmp_path / "report.html"
    html_path.write_text(
        "<html><head><title>行业报告</title></head><body><main>"
        "<h2>人才趋势</h2><p>企业增加 AI Agent 岗位。</p></main></body></html>",
        encoding="utf-8",
    )
    html_source = SourceSpec(
        source_id="report-html",
        source_type="industry_report",
        input=str(html_path),
        input_format="html",
        source_name="研究机构",
    )
    parsed_html = parse_source(html_source, tmp_path, _config())[0]
    assert parsed_html.document.title == "行业报告"
    assert parsed_html.segments[0].section == "人才趋势"

    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("职业标准", level=1)
    document.add_paragraph("掌握模型评测与数据治理能力。")
    docx_path = tmp_path / "standard.docx"
    document.save(docx_path)
    docx_source = SourceSpec(
        source_id="standard-docx",
        source_type="occupational_standard",
        input=str(docx_path),
        input_format="docx",
        source_name="职业标准平台",
    )
    parsed_docx = parse_source(docx_source, tmp_path, _config())[0]
    assert parsed_docx.document.title == "职业标准"
    assert "数据治理" in parsed_docx.document.text

    for parsed in (parsed_text, parsed_html, parsed_docx):
        for item in build_evidence(parsed, _config()):
            assert parsed.document.text[item.char_start : item.char_end] == item.text


def test_low_text_pdf_is_marked_needs_ocr(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    pdf_path = tmp_path / "scan.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    manifest_path = _write_manifest(
        tmp_path / "sources.yaml",
        [
            {
                "source_id": "scan-standard",
                "source_type": "occupational_standard",
                "input": "scan.pdf",
                "input_format": "pdf",
                "source_name": "标准发布机构",
            }
        ],
    )

    result = ingest_manifest(manifest_path, tmp_path / "warehouse", _config())
    document = Warehouse(tmp_path / "warehouse").load("documents")[0]
    assert document.parse_status == "needs_ocr"
    assert result["source_summaries"][0]["status"] == "needs_ocr"
    assert Warehouse(tmp_path / "warehouse").load("evidence") == []
