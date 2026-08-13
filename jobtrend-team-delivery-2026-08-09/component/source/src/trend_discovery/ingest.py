from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from .io_utils import sha256_bytes, stable_id
from .parsers import FetchCallable, build_evidence, parse_source
from .schemas import Evidence, ExternalDocument, SourceManifest
from .warehouse import Warehouse


def load_source_manifest(path: str | Path) -> SourceManifest:
    """Load and strictly validate a ``source_manifest_v1`` YAML file."""

    manifest_path = Path(path).expanduser().resolve()
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid source manifest YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("source manifest must be a YAML mapping")
    return SourceManifest.model_validate(payload)


def ingest_manifest(
    manifest_path: str | Path,
    warehouse_dir: str | Path,
    config: Mapping[str, Any],
    fetcher: FetchCallable | None = None,
) -> dict[str, Any]:
    """Parse enabled manifest sources and atomically merge them into a warehouse.

    Individual source failures are isolated and included in the returned run
    summary. Manifest validation and warehouse commit errors remain fatal.
    """

    started_at = datetime.now(timezone.utc)
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    manifest_bytes = resolved_manifest_path.read_bytes()
    manifest = load_source_manifest(resolved_manifest_path)
    manifest_sha256 = sha256_bytes(manifest_bytes)
    run_id = stable_id("ingest", manifest_sha256, started_at.isoformat(), length=24)

    documents: list[ExternalDocument] = []
    evidence: list[Evidence] = []
    source_summaries: list[dict[str, Any]] = []
    enabled_sources = [source for source in manifest.sources if source.enabled]

    for source in enabled_sources:
        try:
            parsed_documents = parse_source(
                source,
                resolved_manifest_path.parent,
                config,
                fetcher=fetcher,
                collected_at=started_at,
            )
            source_evidence: list[Evidence] = []
            parse_status_counts = {"parsed": 0, "needs_ocr": 0, "failed": 0}
            for parsed in parsed_documents:
                documents.append(parsed.document)
                parse_status_counts[parsed.document.parse_status] += 1
                chunks = build_evidence(parsed, config)
                evidence.extend(chunks)
                source_evidence.extend(chunks)
            source_summaries.append(
                {
                    "source_id": source.source_id,
                    "source_name": source.source_name,
                    "source_type": source.source_type,
                    "status": "needs_ocr" if parse_status_counts["needs_ocr"] else "completed",
                    "documents": len(parsed_documents),
                    "evidence_chunks": len(source_evidence),
                    "parse_status_counts": parse_status_counts,
                }
            )
        except Exception as exc:  # one malformed source must not discard successful sources
            source_summaries.append(
                {
                    "source_id": source.source_id,
                    "source_name": source.source_name,
                    "source_type": source.source_type,
                    "status": "failed",
                    "documents": 0,
                    "evidence_chunks": 0,
                    "parse_status_counts": {"parsed": 0, "needs_ocr": 0, "failed": 1},
                    "error": _safe_error(exc),
                }
            )

    completed_at = datetime.now(timezone.utc)
    failure_count = sum(item["status"] == "failed" for item in source_summaries)
    run_status = "completed"
    if failure_count == len(enabled_sources) and enabled_sources:
        run_status = "failed"
    elif failure_count:
        run_status = "partial"

    summary: dict[str, Any] = {
        "schema_version": "ingest_run_summary_v1",
        "run_id": run_id,
        "status": run_status,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "manifest_sha256": manifest_sha256,
        "sources_declared": len(manifest.sources),
        "sources_enabled": len(enabled_sources),
        "sources_succeeded": len(enabled_sources) - failure_count,
        "sources_failed": failure_count,
        "documents_parsed": len(documents),
        "evidence_chunks": len(evidence),
        "source_summaries": source_summaries,
    }

    warehouse = Warehouse(warehouse_dir)
    warehouse_result = warehouse.upsert(documents, evidence, run_summary=summary)
    summary["warehouse"] = warehouse_result
    return summary


def _safe_error(exc: Exception) -> str:
    """Return a short diagnostic without echoing source URLs or query secrets."""

    message = str(exc).replace("\n", " ").strip()
    message = re.sub(r"https?://\S+", "[redacted-url]", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)(api[-_]?key|token|signature|secret)=([^&\s]+)",
        r"\1=[redacted]",
        message,
    )
    if len(message) > 300:
        message = message[:297] + "..."
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


__all__ = ["ingest_manifest", "load_source_manifest"]
