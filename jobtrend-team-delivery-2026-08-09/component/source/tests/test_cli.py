from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from trend_discovery.batch import SUBMIT_CONFIRMATION
from trend_discovery.cli import build_parser, main
from trend_discovery.schemas import Evidence, ExternalDocument
from trend_discovery.warehouse import Warehouse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> Path:
    value = yaml.safe_load((PROJECT_ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
    value["paths"] = {
        "warehouse": str(tmp_path / "warehouse"),
        "runs": str(tmp_path / "runs"),
        "qdrant": str(tmp_path / "qdrant"),
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _document_and_evidence() -> tuple[ExternalDocument, Evidence]:
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    document = ExternalDocument(
        document_id="cli-doc-1",
        source_type="job",
        source_name="test-careers",
        title="AI Agent 工程师",
        text="负责 Agent 开发，需要 Python。",
        raw_sha256="a" * 64,
        parser_version="test",
        company="测试企业",
        collected_at=now,
    )
    evidence = Evidence(
        evidence_id="cli-ev-1",
        document_id=document.document_id,
        source_type="job",
        text=document.text,
        text_sha256="b" * 64,
        char_start=0,
        char_end=len(document.text),
    )
    return document, evidence


def test_help_lists_the_fixed_public_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--help"])
    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    for command in (
        "ingest",
        "import-kg",
        "prepare",
        "submit",
        "status",
        "download",
        "analyze",
        "review-export",
        "review-import",
        "export",
        "run-all",
    ):
        assert command in help_text


def test_usage_errors_are_json_and_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "CLIUsageError"


def test_prepare_and_submit_are_network_free_until_exact_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    config_path = _config(tmp_path)
    document, evidence = _document_and_evidence()
    Warehouse(tmp_path / "warehouse").upsert([document], [evidence])
    batch_dir = tmp_path / "batch"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "prepare",
                "--output",
                str(batch_dir),
                "--run-id",
                "cli-run",
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["result"]["phase"] == "prepared"
    assert prepared["result"]["dry_run"] is True
    assert prepared["result"]["paid_request_submitted"] is False
    state_path = batch_dir / "batch_state.json"

    assert main(["--config", str(config_path), "submit", "--state", str(state_path)]) == 0
    dry_submit = json.loads(capsys.readouterr().out)
    assert dry_submit["result"]["phase"] == "prepared"
    assert dry_submit["result"]["executed"] is False
    assert dry_submit["result"]["dry_run"] is True

    assert (
        main(
            [
                "--config",
                str(config_path),
                "submit",
                "--state",
                str(state_path),
                "--execute",
                "--confirm",
                "yes",
            ]
        )
        == 4
    )
    denied = json.loads(capsys.readouterr().err)
    assert denied["error"]["type"] == "PermissionError"
    assert SUBMIT_CONFIRMATION in denied["error"]["message"]


def test_sample_run_all_ingests_then_analyzes_and_checkpoints(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _config(tmp_path)
    output = tmp_path / "analysis-output"
    events: list[str] = []

    def fake_analyze(**kwargs: object) -> dict[str, object]:
        events.append("analyze")
        warehouse = Warehouse(Path(str(kwargs["warehouse_dir"])))
        # 120 synthetic JDs plus the policy and report fixtures.
        assert len(warehouse.load_documents()) == 122
        output_dir = Path(str(kwargs["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = output_dir / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        return {
            "run_id": "sample-run",
            "output_dir": str(output_dir),
            "manifest": str(manifest),
            "counts": {"documents": 122},
        }

    def fake_mark(runs_root: str | Path, result: object) -> Path:
        events.append("checkpoint")
        path = Path(runs_root) / "latest_success.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr("trend_discovery.cli.analyze_warehouse", fake_analyze)
    monkeypatch.setattr("trend_discovery.cli.mark_latest_success", fake_mark)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "run-all",
                "--sources",
                str(PROJECT_ROOT / "data" / "samples" / "sources.yaml"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["ingest"]["documents_parsed"] == 122
    assert payload["result"]["analysis"]["run_id"] == "sample-run"
    assert events == ["analyze", "checkpoint"]
