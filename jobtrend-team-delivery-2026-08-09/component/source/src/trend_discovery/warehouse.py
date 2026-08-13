from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Mapping, Sequence

from .io_utils import read_jsonl, write_jsonl
from .schemas import Evidence, ExternalDocument


DatasetName = Literal["documents", "external_documents", "evidence", "runs", "run_summaries"]


_DOCUMENT_COLUMNS = (
    "schema_version",
    "document_id",
    "source_type",
    "source_name",
    "title",
    "text",
    "raw_sha256",
    "parser_version",
    "parse_status",
    "publisher",
    "uri",
    "external_id",
    "company",
    "industry",
    "region",
    "published_at",
    "collected_at",
    "license",
    "metadata",
)

_EVIDENCE_COLUMNS = (
    "schema_version",
    "evidence_id",
    "document_id",
    "source_type",
    "text",
    "text_sha256",
    "uri",
    "page",
    "section",
    "char_start",
    "char_end",
)

_CREATE_DOCUMENTS = """
CREATE TABLE external_documents (
    schema_version VARCHAR NOT NULL,
    document_id VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    text VARCHAR NOT NULL,
    raw_sha256 VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    parse_status VARCHAR NOT NULL,
    publisher VARCHAR,
    uri VARCHAR,
    external_id VARCHAR,
    company VARCHAR,
    industry VARCHAR,
    region VARCHAR,
    published_at VARCHAR,
    collected_at VARCHAR NOT NULL,
    license VARCHAR,
    metadata VARCHAR NOT NULL
)
"""

_CREATE_EVIDENCE = """
CREATE TABLE evidence (
    schema_version VARCHAR NOT NULL,
    evidence_id VARCHAR NOT NULL,
    document_id VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    text VARCHAR NOT NULL,
    text_sha256 VARCHAR NOT NULL,
    uri VARCHAR,
    page BIGINT,
    section VARCHAR,
    char_start BIGINT,
    char_end BIGINT
)
"""


class Warehouse:
    """Versionless local fact store backed by Parquet and a DuckDB mirror.

    Parquet is the authoritative representation. JSONL files are deterministic
    interoperability exports, while the DuckDB file provides convenient SQL
    access and persisted run/source summaries.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.documents_parquet = self.root / "external_documents.parquet"
        self.evidence_parquet = self.root / "evidence.parquet"
        self.documents_jsonl = self.root / "external_documents.jsonl"
        self.evidence_jsonl = self.root / "evidence.jsonl"
        self.runs_jsonl = self.root / "ingest_runs.jsonl"
        self.database_path = self.root / "warehouse.duckdb"
        self.lock_path = self.root / ".warehouse.lock"

    def upsert(
        self,
        documents: Iterable[ExternalDocument | Mapping[str, Any]],
        evidence: Iterable[Evidence | Mapping[str, Any]],
        *,
        run_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, int]:
        """Merge by stable IDs and atomically replace all warehouse artifacts."""

        _duckdb()
        incoming_documents = [
            value if isinstance(value, ExternalDocument) else ExternalDocument.model_validate(value)
            for value in documents
        ]
        incoming_evidence = [
            value if isinstance(value, Evidence) else Evidence.model_validate(value)
            for value in evidence
        ]
        incoming_document_map = {item.document_id: item for item in incoming_documents}
        incoming_evidence_map = {item.evidence_id: item for item in incoming_evidence}

        for item in incoming_evidence_map.values():
            if item.document_id not in incoming_document_map:
                # References to an unchanged document already in the warehouse are
                # checked again below after the existing state is loaded.
                continue

        with self._lock(exclusive=True):
            existing_documents = {item.document_id: item for item in self._load_documents_unlocked()}
            existing_evidence = {item.evidence_id: item for item in self._load_evidence_unlocked()}
            existing_runs = self._load_runs_unlocked()

            known_document_ids = set(existing_documents) | set(incoming_document_map)
            dangling = sorted(
                item.evidence_id
                for item in incoming_evidence_map.values()
                if item.document_id not in known_document_ids
            )
            if dangling:
                preview = ", ".join(dangling[:3])
                raise ValueError(f"evidence references unknown documents: {preview}")

            inserted_documents = len(set(incoming_document_map) - set(existing_documents))
            updated_documents = sum(
                document_id in existing_documents
                and _model_payload(existing_documents[document_id]) != _model_payload(document)
                for document_id, document in incoming_document_map.items()
            )
            unchanged_documents = len(incoming_document_map) - inserted_documents - updated_documents

            incoming_document_ids = set(incoming_document_map)
            stale_evidence_ids = {
                evidence_id
                for evidence_id, item in existing_evidence.items()
                if item.document_id in incoming_document_ids and evidence_id not in incoming_evidence_map
            }
            retained_evidence = {
                evidence_id: item
                for evidence_id, item in existing_evidence.items()
                if item.document_id not in incoming_document_ids
            }
            inserted_evidence = len(set(incoming_evidence_map) - set(existing_evidence))
            updated_evidence = sum(
                evidence_id in existing_evidence
                and _model_payload(existing_evidence[evidence_id]) != _model_payload(item)
                for evidence_id, item in incoming_evidence_map.items()
            )
            unchanged_evidence = len(incoming_evidence_map) - inserted_evidence - updated_evidence

            merged_documents = {**existing_documents, **incoming_document_map}
            merged_evidence = {**retained_evidence, **incoming_evidence_map}
            statistics = {
                "documents_inserted": inserted_documents,
                "documents_updated": updated_documents,
                "documents_unchanged": unchanged_documents,
                "documents_total": len(merged_documents),
                "evidence_inserted": inserted_evidence,
                "evidence_updated": updated_evidence,
                "evidence_unchanged": unchanged_evidence,
                "evidence_deleted": len(stale_evidence_ids),
                "evidence_total": len(merged_evidence),
            }

            runs_by_id = {
                str(item.get("run_id", f"legacy-{index}")): item
                for index, item in enumerate(existing_runs, start=1)
            }
            if run_summary is not None:
                stored_summary = copy.deepcopy(dict(run_summary))
                run_id = str(stored_summary.get("run_id", "")).strip()
                if not run_id:
                    raise ValueError("run_summary.run_id is required")
                stored_summary["warehouse"] = statistics
                _assert_json_serializable(stored_summary)
                runs_by_id[run_id] = stored_summary

            ordered_documents = [merged_documents[key] for key in sorted(merged_documents)]
            ordered_evidence = [merged_evidence[key] for key in sorted(merged_evidence)]
            ordered_runs = [runs_by_id[key] for key in sorted(runs_by_id)]
            self._write_generation(ordered_documents, ordered_evidence, ordered_runs)
            return statistics

    def load(self, dataset: DatasetName = "documents") -> list[Any]:
        """Load one canonical dataset as validated models (or dicts for runs)."""

        with self._lock(exclusive=False):
            if dataset in {"documents", "external_documents"}:
                return self._load_documents_unlocked()
            if dataset == "evidence":
                return self._load_evidence_unlocked()
            if dataset in {"runs", "run_summaries"}:
                return self._load_runs_unlocked()
        raise ValueError(f"unknown warehouse dataset: {dataset}")

    def export(self, output_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
        """Regenerate portable JSONL exports from authoritative Parquet facts."""

        target = Path(output_dir).expanduser().resolve() if output_dir else self.root
        target.mkdir(parents=True, exist_ok=True)
        documents = self.load("documents")
        evidence = self.load("evidence")
        runs = self.load("runs")
        documents_path = target / "external_documents.jsonl"
        evidence_path = target / "evidence.jsonl"
        runs_path = target / "ingest_runs.jsonl"
        write_jsonl(documents_path, documents)
        write_jsonl(evidence_path, evidence)
        write_jsonl(runs_path, runs)
        return {
            "external_documents": {"path": str(documents_path), "records": len(documents)},
            "evidence": {"path": str(evidence_path), "records": len(evidence)},
            "ingest_runs": {"path": str(runs_path), "records": len(runs)},
        }

    def load_documents(self) -> list[ExternalDocument]:
        return self.load("documents")

    def load_evidence(self) -> list[Evidence]:
        return self.load("evidence")

    def _load_documents_unlocked(self) -> list[ExternalDocument]:
        if self.documents_parquet.exists():
            rows = _read_parquet(self.documents_parquet, _DOCUMENT_COLUMNS)
            result: list[ExternalDocument] = []
            for row in rows:
                metadata = row.get("metadata")
                if isinstance(metadata, str):
                    row["metadata"] = json.loads(metadata) if metadata else {}
                result.append(ExternalDocument.model_validate(row))
            return result
        if self.documents_jsonl.exists():
            return [ExternalDocument.model_validate(row) for row in read_jsonl(self.documents_jsonl)]
        return []

    def _load_evidence_unlocked(self) -> list[Evidence]:
        if self.evidence_parquet.exists():
            return [Evidence.model_validate(row) for row in _read_parquet(self.evidence_parquet, _EVIDENCE_COLUMNS)]
        if self.evidence_jsonl.exists():
            return [Evidence.model_validate(row) for row in read_jsonl(self.evidence_jsonl)]
        return []

    def _load_runs_unlocked(self) -> list[dict[str, Any]]:
        if not self.runs_jsonl.exists():
            return []
        return list(read_jsonl(self.runs_jsonl))

    def _write_generation(
        self,
        documents: Sequence[ExternalDocument],
        evidence: Sequence[Evidence],
        runs: Sequence[Mapping[str, Any]],
    ) -> None:
        duckdb = _duckdb()
        stage = Path(tempfile.mkdtemp(prefix=".warehouse-stage-", dir=self.root))
        try:
            stage_documents_jsonl = stage / self.documents_jsonl.name
            stage_evidence_jsonl = stage / self.evidence_jsonl.name
            stage_runs_jsonl = stage / self.runs_jsonl.name
            stage_documents_parquet = stage / self.documents_parquet.name
            stage_evidence_parquet = stage / self.evidence_parquet.name
            stage_database = stage / self.database_path.name

            write_jsonl(stage_documents_jsonl, documents)
            write_jsonl(stage_evidence_jsonl, evidence)
            write_jsonl(stage_runs_jsonl, runs)

            connection = duckdb.connect(str(stage_database))
            try:
                connection.execute("PRAGMA disable_progress_bar")
                connection.execute(_CREATE_DOCUMENTS)
                connection.execute(_CREATE_EVIDENCE)
                if documents:
                    connection.executemany(
                        f"INSERT INTO external_documents VALUES ({','.join('?' for _ in _DOCUMENT_COLUMNS)})",
                        [_document_row(item) for item in documents],
                    )
                if evidence:
                    connection.executemany(
                        f"INSERT INTO evidence VALUES ({','.join('?' for _ in _EVIDENCE_COLUMNS)})",
                        [_evidence_row(item) for item in evidence],
                    )
                connection.execute(
                    f"COPY external_documents TO '{_sql_path(stage_documents_parquet)}' "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                connection.execute(
                    f"COPY evidence TO '{_sql_path(stage_evidence_parquet)}' (FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                _create_run_tables(connection, runs)
                connection.execute("CHECKPOINT")
            finally:
                connection.close()

            replacements = (
                (stage_documents_parquet, self.documents_parquet),
                (stage_evidence_parquet, self.evidence_parquet),
                (stage_documents_jsonl, self.documents_jsonl),
                (stage_evidence_jsonl, self.evidence_jsonl),
                (stage_database, self.database_path),
                (stage_runs_jsonl, self.runs_jsonl),
            )
            for source, target in replacements:
                os.replace(source, target)
            _fsync_directory(self.root)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            try:
                import fcntl

                operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(handle.fileno(), operation)
            except ImportError:  # pragma: no cover - Windows fallback
                fcntl = None  # type: ignore[assignment]
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _create_run_tables(connection: Any, runs: Sequence[Mapping[str, Any]]) -> None:
    connection.execute(
        """
        CREATE TABLE ingest_runs (
            run_id VARCHAR NOT NULL,
            status VARCHAR,
            started_at VARCHAR,
            completed_at VARCHAR,
            manifest_sha256 VARCHAR,
            summary_json VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE source_runs (
            run_id VARCHAR NOT NULL,
            source_id VARCHAR,
            source_name VARCHAR,
            source_type VARCHAR,
            status VARCHAR,
            documents BIGINT,
            evidence_chunks BIGINT,
            summary_json VARCHAR NOT NULL
        )
        """
    )
    run_rows: list[tuple[Any, ...]] = []
    source_rows: list[tuple[Any, ...]] = []
    for run in runs:
        run_id = str(run.get("run_id", ""))
        run_rows.append(
            (
                run_id,
                _optional_string(run.get("status")),
                _optional_string(run.get("started_at")),
                _optional_string(run.get("completed_at")),
                _optional_string(run.get("manifest_sha256")),
                json.dumps(run, ensure_ascii=False, sort_keys=True, default=str),
            )
        )
        source_summaries = run.get("source_summaries", [])
        if not isinstance(source_summaries, list):
            continue
        for source in source_summaries:
            if not isinstance(source, Mapping):
                continue
            source_rows.append(
                (
                    run_id,
                    _optional_string(source.get("source_id")),
                    _optional_string(source.get("source_name")),
                    _optional_string(source.get("source_type")),
                    _optional_string(source.get("status")),
                    int(source.get("documents", 0) or 0),
                    int(source.get("evidence_chunks", 0) or 0),
                    json.dumps(source, ensure_ascii=False, sort_keys=True, default=str),
                )
            )
    if run_rows:
        connection.executemany("INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?)", run_rows)
    if source_rows:
        connection.executemany("INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", source_rows)


def _document_row(document: ExternalDocument) -> tuple[Any, ...]:
    value = document.model_dump(mode="json")
    return tuple(
        json.dumps(value[column], ensure_ascii=False, sort_keys=True, default=str)
        if column == "metadata"
        else value[column]
        for column in _DOCUMENT_COLUMNS
    )


def _evidence_row(evidence: Evidence) -> tuple[Any, ...]:
    value = evidence.model_dump(mode="json")
    return tuple(value[column] for column in _EVIDENCE_COLUMNS)


def _read_parquet(path: Path, columns: Sequence[str]) -> list[dict[str, Any]]:
    duckdb = _duckdb()
    connection = duckdb.connect(database=":memory:")
    try:
        projection = ", ".join(f'"{column}"' for column in columns)
        rows = connection.execute(
            f"SELECT {projection} FROM read_parquet(?) ORDER BY 2",
            [str(path)],
        ).fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        connection.close()


def _duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - installation error
        raise RuntimeError("duckdb is required for the warehouse; install project dependencies") from exc
    return duckdb


def _model_payload(value: ExternalDocument | Evidence) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _assert_json_serializable(value: Any) -> None:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        raise ValueError("run_summary must be JSON serializable") from exc


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


__all__ = ["DatasetName", "Warehouse"]
