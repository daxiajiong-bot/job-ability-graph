"""SQLite connection manager and schema initialization."""

from __future__ import annotations

import atexit
import sqlite3
import weakref
from pathlib import Path
from threading import local

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    last_active_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    document_type   TEXT NOT NULL,
    text            TEXT NOT NULL,
    title           TEXT,
    company_name    TEXT,
    industry        TEXT,
    location        TEXT,
    salary_range    TEXT,
    experience      TEXT,
    education       TEXT,
    skills          TEXT,
    source_system   TEXT NOT NULL,
    source_id       TEXT,
    url             TEXT,
    metadata        TEXT,
    content_digest  TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS profiles (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    document_id     TEXT NOT NULL,
    profile_type    TEXT NOT NULL,
    state           TEXT NOT NULL,
    attributes      TEXT,
    evidence        TEXT,
    warnings        TEXT,
    implementation  TEXT,
    artifacts       TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_user_type
    ON documents(user_id, document_type);
CREATE INDEX IF NOT EXISTS idx_documents_type
    ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_profiles_user
    ON profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_document
    ON profiles(document_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_doc_type
    ON profiles(document_id, profile_type);

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    task_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    document_id     TEXT NOT NULL,
    profile_id      TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);

CREATE TABLE IF NOT EXISTS knowledge_graphs (
    id                      TEXT PRIMARY KEY,
    document_ids            TEXT NOT NULL,
    candidate_profile_ids   TEXT NOT NULL,
    job_profile_ids         TEXT NOT NULL,
    nodes                   TEXT NOT NULL,
    edges                   TEXT NOT NULL,
    state                   TEXT NOT NULL,
    implementation          TEXT NOT NULL,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id                      TEXT PRIMARY KEY,
    candidate_profile_id    TEXT NOT NULL,
    job_profile_id          TEXT NOT NULL,
    score                   REAL,
    decision                TEXT NOT NULL,
    strengths               TEXT,
    gaps                    TEXT,
    learning_path           TEXT,
    document_evidence       TEXT,
    graph_evidence          TEXT,
    details                 TEXT,
    summary                 TEXT,
    warnings                TEXT,
    state                   TEXT NOT NULL,
    implementation          TEXT NOT NULL,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id                      TEXT PRIMARY KEY,
    match_id                TEXT NOT NULL,
    language                TEXT NOT NULL,
    sections                TEXT,
    state                   TEXT NOT NULL,
    implementation          TEXT NOT NULL,
    created_at              TEXT NOT NULL
);
"""


def _close_on_gc(ref: weakref.ref) -> None:
    """Weak-ref finalizer: close connection when DatabaseManager is garbage collected."""
    conn = getattr(ref, "_finalizer_conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


class DatabaseManager:
    """Thread-safe SQLite connection manager with automatic schema creation."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._local = local()
        # Initialize schema on first connection
        conn = self.connection
        conn.executescript(_SCHEMA_SQL)
        self._ensure_match_columns(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Auto-close on garbage collection (handles test cleanup)
        self._finalizer = weakref.finalize(self, self._cleanup, conn)

    @staticmethod
    def _cleanup(conn: sqlite3.Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _ensure_match_columns(conn: sqlite3.Connection) -> None:
        """Migrate match metadata columns for databases created by older builds."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
        for name in ("details", "summary", "warnings"):
            if name not in columns:
                conn.execute(f"ALTER TABLE matches ADD COLUMN {name} TEXT")
        conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.connection = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            self._local.connection = None

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        return self.connection.executemany(sql, params_list)

    def commit(self) -> None:
        self.connection.commit()

    def table_count(self, table: str) -> int:
        row = self.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return row[0] if row else 0
