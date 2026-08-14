"""SQLite-backed resource repository with user isolation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from backend.app.domain.entities import (
    GeneratedReport,
    KnowledgeGraphSnapshot,
    MatchAssessment,
    Profile,
    ProfileType,
    SourceDocument,
    Task,
    TaskStatus,
)
from backend.app.domain.errors import PermissionDeniedError, ResourceConflictError, ResourceNotFoundError
from backend.app.infrastructure.sqlite.db import DatabaseManager
from backend.app.infrastructure.sqlite.models import DocumentRow, ProfileRow


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resource_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _extract_display_fields(document_type: str, text: str) -> dict[str, Any]:
    """Extract list-friendly fields without replacing the formal profile parser."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields: dict[str, Any] = {}

    def value_after(labels: tuple[str, ...]) -> str | None:
        for line in lines[:12]:
            for label in labels:
                match = re.search(rf"{re.escape(label)}\s*[：:、]?\s*(.+)", line)
                if match:
                    return match.group(1).strip().split("  ")[0][:120]
        return None

    if document_type == "resume":
        name = value_after(("姓名", "名字", "候选人"))
        if name:
            fields["candidate_name"] = name
            fields["display_name"] = name
        education = value_after(("学历", "教育背景"))
        experience = value_after(("工作经验", "经验", "工作年限"))
        if education:
            fields["education"] = education
        if experience:
            fields["experience"] = experience
    elif document_type == "jd":
        title = value_after(("岗位名称", "职位名称", "招聘岗位", "职位"))
        if not title:
            title = next((line for line in lines[:5] if len(line) <= 40), None)
        if title:
            fields["title"] = title
            fields["job_title"] = title
        company = value_after(("公司", "公司名称", "企业"))
        if company:
            fields["company_name"] = company
        location = value_after(("工作地点", "地点", "工作城市"))
        if location:
            fields["location"] = location
        salary = value_after(("薪资范围", "薪资", "薪酬"))
        if salary:
            fields["salary_range"] = salary
        experience = value_after(("经验要求", "工作经验", "经验"))
        if experience:
            fields["experience"] = experience

    skills = []
    for line in lines:
        if any(label in line for label in ("技能", "技术栈", "任职要求", "岗位要求")):
            skills.extend(re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}|[一-鿿]{2,8}", line))
    if skills:
        fields["skills"] = list(dict.fromkeys(skills))[:30]
    return fields


class SQLiteResourceRepository:
    """Persistent repository backed by SQLite. Supports user-scoped access."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ── User management ──────────────────────────────────

    def ensure_user(self, user_id: str) -> str:
        """Create user if not exists, update last_active_at. Returns user_id."""
        now = _utc_now()
        self._db.execute(
            """INSERT INTO users (user_id, created_at, last_active_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET last_active_at = excluded.last_active_at""",
            (user_id, now, now),
        )
        self._db.commit()
        return user_id

    def create_user(self, user_id: str, username: str, password_hash: str,
                    role: str = "job_seeker", display_name: str | None = None) -> dict:
        """Create a new user with auth credentials. Returns user dict."""
        now = _utc_now()
        try:
            self._db.execute(
                """INSERT INTO users (user_id, username, password_hash, role, display_name, created_at, last_active_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, password_hash, role, display_name, now, now),
            )
            self._db.commit()
        except Exception as e:
            if "UNIQUE" in str(e) and "username" in str(e):
                raise ResourceConflictError(f"用户名 '{username}' 已被注册")
            raise
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "display_name": display_name,
        }

    def get_user_by_username(self, username: str) -> dict | None:
        """Get user by username. Returns dict or None."""
        row = self._db.execute(
            "SELECT user_id, username, password_hash, role, display_name FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "display_name": row[4],
        }

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Get user by user_id. Returns dict or None."""
        row = self._db.execute(
            "SELECT user_id, username, role, display_name, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "role": row[2],
            "display_name": row[3],
            "created_at": row[4],
        }

    def get_user_document_count(self, user_id: str) -> dict:
        """Count documents visible to a user (system + own)."""
        rows = self._db.execute(
            """SELECT document_type, COUNT(*) FROM documents
               WHERE user_id = 'system' OR user_id = ?
               GROUP BY document_type""",
            (user_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ── Document operations ──────────────────────────────

    def add_document(self, document: SourceDocument, user_id: str = "system") -> SourceDocument:
        """Store a document. Extracts structured fields from metadata for querying."""
        metadata = document.metadata or {}
        source = document.source or {}

        extracted = _extract_display_fields(document.document_type.value, document.text)
        metadata = {**extracted, **metadata}

        # Extract display fields from metadata or source
        title = metadata.get("title") or metadata.get("job_title")
        company_name = metadata.get("company_name")
        industry = metadata.get("industry")
        location = metadata.get("location")
        salary_range = metadata.get("salary_range")
        experience = metadata.get("experience")
        education = metadata.get("education")
        skills = metadata.get("skills")
        if isinstance(skills, list):
            skills = json.dumps(skills, ensure_ascii=False)
        source_system = source.get("source_system", "manual")
        source_id = source.get("external_id") or source.get("source_id")
        url = metadata.get("url")

        self._db.execute(
            """INSERT OR REPLACE INTO documents
               (id, user_id, document_type, text, title, company_name, industry,
                location, salary_range, experience, education, skills,
                source_system, source_id, url, metadata, content_digest, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document.id, user_id, document.document_type.value, document.text,
                title, company_name, industry, location, salary_range,
                experience, education, skills, source_system, source_id, url,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
                document.content_digest, document.created_at,
            ),
        )
        self._db.commit()
        return document

    def get_document(self, document_id: str) -> SourceDocument:
        row = self._db.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"document '{document_id}' was not found")
        return self._row_to_document(row)

    def delete_document(self, document_id: str, user_id: str) -> None:
        """Delete a document and its associated profiles. Only owner can delete; system docs are protected."""
        row = self._db.execute(
            "SELECT user_id FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"document '{document_id}' was not found")
        if row[0] == "system":
            raise PermissionDeniedError("system documents cannot be deleted")
        if row[0] != user_id:
            raise PermissionDeniedError("you can only delete your own documents")
        # Cascade delete profiles referencing this document
        self._db.execute("DELETE FROM profiles WHERE document_id = ?", (document_id,))
        self._db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        self._db.commit()

    def list_documents(
        self,
        user_id: str,
        document_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List documents visible to a user (system + own uploads)."""
        conditions = ["(user_id = 'system' OR user_id = ?)"]
        params: list[Any] = [user_id]

        if document_type:
            conditions.append("document_type = ?")
            params.append(document_type)

        where = " AND ".join(conditions)

        # Total count
        count_row = self._db.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where}", tuple(params)
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Fetch page
        params.extend([limit, offset])
        rows = self._db.execute(
            f"""SELECT * FROM documents WHERE {where}
                ORDER BY
                    CASE WHEN user_id = 'system' THEN 1 ELSE 0 END,
                    created_at DESC
                LIMIT ? OFFSET ?""",
            tuple(params),
        ).fetchall()

        items = [DocumentRow(**dict(r)).to_public() for r in rows]
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def get_user_document_count(self, user_id: str) -> dict[str, int]:
        """Get document counts for a user."""
        jd_row = self._db.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ? AND document_type = 'jd'",
            (user_id,),
        ).fetchone()
        resume_row = self._db.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ? AND document_type = 'resume'",
            (user_id,),
        ).fetchone()
        system_jd_row = self._db.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = 'system' AND document_type = 'jd'",
        ).fetchone()
        return {
            "user_jds": jd_row[0] if jd_row else 0,
            "user_resumes": resume_row[0] if resume_row else 0,
            "system_jds": system_jd_row[0] if system_jd_row else 0,
        }

    def search_documents_by_skills(
        self,
        skills: list[str],
        document_type: str,
        user_id: str,
        exclude_doc_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search documents by skill keywords, ranked by number of matching skills.

        Uses the ``skills`` JSON column stored on each document row.
        Returns a list of dicts with ``document`` and ``match_count`` keys.
        """
        if not skills:
            return []

        # Build SQL: count how many input skills appear in the document's skills field
        # skills column is a JSON array string like '["Python", "React", ...]'
        score_params: list[Any] = []
        for skill in skills[:30]:  # cap to avoid huge queries
            pattern = f"%{skill}%"
            score_params.extend([pattern, pattern, pattern])

        score_expr = " + ".join(
            f"CASE WHEN (skills LIKE ? OR title LIKE ? OR text LIKE ?) THEN 1 ELSE 0 END"
            for _ in skills[:30]
        )

        where_parts = [
            "(user_id = 'system' OR user_id = ?)",
            "document_type = ?",
        ]
        where_params: list[Any] = [user_id, document_type]

        if exclude_doc_id:
            where_parts.append("id != ?")
            where_params.append(exclude_doc_id)

        where_clause = " AND ".join(where_parts)

        sql = f"""
            SELECT * FROM (
                SELECT *, ({score_expr}) as match_score
                FROM documents
                WHERE {where_clause}
            )
            WHERE match_score > 0
            ORDER BY match_score DESC
            LIMIT ?
        """
        # Bind in text order: score-expression params first, then WHERE params.
        query_params = [*score_params, *where_params, limit]

        rows = self._db.execute(sql, tuple(query_params)).fetchall()
        results = []
        for row in rows:
            row_dict = dict(row)
            match_score = row_dict.pop("match_score", 0)
            doc = DocumentRow(**{k: row_dict[k] for k in row_dict if k != "match_score"}).to_public()
            results.append({"document": doc, "match_count": match_score})
        return results

    def search_documents_for_recommendation(
        self,
        skills: list[str],
        document_type: str,
        user_id: str,
        exclude_doc_id: str | None = None,
        limit: int = 40,
        filters: dict[str, Any] | None = None,
        include_hr_documents: bool = False,
    ) -> list[dict]:
        """Recommendation-oriented candidate search.

        Same skill-overlap scoring as :meth:`search_documents_by_skills`, but:
        - searches the union of system documents and the current user's documents,
        - optionally includes documents uploaded by HR users (recruiter postings),
        - supports lightweight ``filters`` (LIKE clauses on metadata columns).

        Filters may contain: ``location``, ``industry``, ``company_name``,
        ``keyword`` (title/text), ``experience`` and ``education``. Numeric
        filters (``salary_min``/``salary_max``/``years_min``) are applied by
        the caller after retrieval because salary ranges are free text.
        """
        if not skills:
            return []

        score_expr_parts = []
        for skill in skills[:30]:
            score_expr_parts.append("(skills LIKE ? OR title LIKE ? OR text LIKE ?)")

        visibility = "((user_id = 'system' OR user_id = ?)"
        if include_hr_documents:
            visibility += " OR user_id IN (SELECT user_id FROM users WHERE role = 'hr'))"
        else:
            visibility += ")"
        where_parts = [
            visibility,
            "document_type = ?",
        ]
        where_params: list[Any] = [user_id, document_type]

        # Optional text filters → ANDed LIKE clauses
        text_filters = {
            "location": "location",
            "industry": "industry",
            "company_name": "company_name",
            "experience": "experience",
            "education": "education",
        }
        filters = filters or {}
        for key, column in text_filters.items():
            value = filters.get(key)
            if not value:
                continue
            where_parts.append(f"{column} LIKE ?")
            where_params.append(f"%{str(value).strip()}%")

        keyword = filters.get("keyword")
        if keyword:
            where_parts.append("(title LIKE ? OR text LIKE ?)")
            pattern = f"%{str(keyword).strip()}%"
            where_params.extend([pattern, pattern])

        if exclude_doc_id:
            where_parts.append("id != ?")
            where_params.append(exclude_doc_id)

        where_clause = " AND ".join(where_parts)
        score_expr = " + ".join(score_expr_parts)
        score_params = []
        for skill in skills[:30]:
            pattern = f"%{skill}%"
            score_params.extend([pattern, pattern, pattern])

        sql = f"""
            SELECT * FROM (
                SELECT *, ({score_expr}) as match_score
                FROM documents
                WHERE {where_clause}
            )
            WHERE match_score > 0
            ORDER BY match_score DESC
            LIMIT ?
        """
        # Bind in text order: score-expression params first, then WHERE params.
        query_params = [*score_params, *where_params, limit]

        rows = self._db.execute(sql, tuple(query_params)).fetchall()
        results = []
        for row in rows:
            row_dict = dict(row)
            match_score = row_dict.pop("match_score", 0)
            doc = DocumentRow(**{k: row_dict[k] for k in row_dict if k != "match_score"}).to_public()
            results.append({"document": doc, "match_count": match_score})
        return results

    def get_documents_by_ids(self, document_ids: list[str]) -> dict[str, dict]:
        """Fetch multiple documents by id; returns {id: public_dict}."""
        if not document_ids:
            return {}
        placeholders = ",".join("?" for _ in document_ids)
        rows = self._db.execute(
            f"SELECT * FROM documents WHERE id IN ({placeholders})",
            tuple(document_ids),
        ).fetchall()
        return {
            row["id"]: DocumentRow(**dict(row)).to_public()
            for row in rows
        }

    def get_profiles_by_document_ids(self, document_ids: list[str], profile_type: str) -> dict[str, dict]:
        """Get profiles for multiple document IDs. Returns {document_id: profile_public_dict}."""
        if not document_ids:
            return {}
        placeholders = ",".join("?" for _ in document_ids)
        rows = self._db.execute(
            f"""SELECT * FROM profiles
                WHERE document_id IN ({placeholders}) AND profile_type = ?""",
            (*document_ids, profile_type),
        ).fetchall()
        result = {}
        for row in rows:
            row_dict = dict(row)
            profile_row = ProfileRow(**row_dict)
            profile = self._row_to_profile(profile_row)
            result[row_dict["document_id"]] = profile.public()
        return result

    # ── Profile operations ───────────────────────────────

    def add_profile(self, profile: Profile, user_id: str = "system") -> Profile:
        self._db.execute(
            """INSERT INTO profiles
               (id, user_id, document_id, profile_type, state,
                attributes, evidence, warnings, implementation, artifacts, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(document_id, profile_type) DO UPDATE SET
                id=excluded.id,
                user_id=excluded.user_id,
                state=excluded.state,
                attributes=excluded.attributes,
                evidence=excluded.evidence,
                warnings=excluded.warnings,
                implementation=excluded.implementation,
                artifacts=excluded.artifacts,
                created_at=excluded.created_at""",
            (
                profile.id, user_id, profile.source_document_id,
                profile.profile_type.value, profile.state,
                json.dumps(profile.attributes, ensure_ascii=False),
                json.dumps(profile.evidence, ensure_ascii=False),
                json.dumps(profile.warnings, ensure_ascii=False),
                profile.implementation,
                json.dumps(profile.artifacts, ensure_ascii=False),
                profile.created_at,
            ),
        )
        self._db.commit()
        return profile

    def get_profile(self, profile_id: str, expected_type: Optional[ProfileType] = None) -> Profile:
        row = self._db.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"profile '{profile_id}' was not found")
        profile_row = ProfileRow(**dict(row))
        if expected_type is not None:
            pt = ProfileType(profile_row.profile_type)
            if pt is not expected_type:
                raise ResourceConflictError(
                    f"profile '{profile_id}' is '{profile_row.profile_type}', expected '{expected_type.value}'"
                )
        return self._row_to_profile(profile_row)

    def get_profile_by_document(self, document_id: str, profile_type: str) -> Optional[dict[str, Any]]:
        """Get profile by document_id, return public dict or None."""
        row = self._db.execute(
            "SELECT * FROM profiles WHERE document_id = ? AND profile_type = ?",
            (document_id, profile_type),
        ).fetchone()
        if row is None:
            return None
        return ProfileRow(**dict(row)).to_public()

    # ── Task operations ───────────────────────────────────

    def add_task(self, task: Task) -> Task:
        self._db.execute(
            """INSERT INTO tasks (id, task_type, status, document_id, profile_id, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.task_type, task.status.value,
                task.document_id, task.profile_id, task.error,
                task.created_at, task.updated_at,
            ),
        )
        self._db.commit()
        return task

    def get_task(self, task_id: str) -> Task:
        row = self._db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"task '{task_id}' was not found")
        return Task(
            id=row["id"],
            task_type=row["task_type"],
            status=TaskStatus(row["status"]),
            document_id=row["document_id"],
            profile_id=row["profile_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_task(self, task_id: str, **fields: Any) -> Task:
        """Update task fields and return the updated task."""
        allowed = {"status", "profile_id", "error"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_task(task_id)
        if "status" in updates and isinstance(updates["status"], TaskStatus):
            updates["status"] = updates["status"].value
        updates["updated_at"] = _utc_now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        self._db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", tuple(values))
        self._db.commit()
        return self.get_task(task_id)

    # ── Stub operations for graph/match/report ───────────

    def add_graph(self, graph: KnowledgeGraphSnapshot) -> KnowledgeGraphSnapshot:
        self._db.execute(
            """INSERT OR REPLACE INTO knowledge_graphs
               (id, document_ids, candidate_profile_ids, job_profile_ids, nodes, edges,
                state, implementation, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                graph.id,
                json.dumps(graph.document_ids, ensure_ascii=False),
                json.dumps(graph.candidate_profile_ids, ensure_ascii=False),
                json.dumps(graph.job_profile_ids, ensure_ascii=False),
                json.dumps(graph.nodes, ensure_ascii=False),
                json.dumps(graph.edges, ensure_ascii=False),
                graph.state,
                graph.implementation,
                graph.created_at,
            ),
        )
        self._db.commit()
        return graph

    def get_graph(self, graph_id: str) -> KnowledgeGraphSnapshot:
        row = self._db.execute("SELECT * FROM knowledge_graphs WHERE id = ?", (graph_id,)).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"knowledge graph '{graph_id}' not in SQLite store")
        return KnowledgeGraphSnapshot(
            id=row["id"],
            document_ids=json.loads(row["document_ids"]),
            candidate_profile_ids=json.loads(row["candidate_profile_ids"]),
            job_profile_ids=json.loads(row["job_profile_ids"]),
            nodes=json.loads(row["nodes"]),
            edges=json.loads(row["edges"]),
            state=row["state"],
            implementation=row["implementation"],
            created_at=row["created_at"],
        )

    def add_match(self, match: MatchAssessment) -> MatchAssessment:
        self._db.execute(
            """INSERT OR REPLACE INTO matches
               (id, candidate_profile_id, job_profile_id, score, decision,
                strengths, gaps, learning_path, document_evidence, graph_evidence,
                details, summary, warnings, state, implementation, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                match.id, match.candidate_profile_id, match.job_profile_id,
                match.score, match.decision,
                json.dumps(match.strengths, ensure_ascii=False),
                json.dumps(match.gaps, ensure_ascii=False),
                json.dumps(match.learning_path, ensure_ascii=False),
                json.dumps(match.document_evidence, ensure_ascii=False),
                json.dumps(match.graph_evidence, ensure_ascii=False),
                json.dumps(match.details, ensure_ascii=False),
                match.summary,
                json.dumps(match.warnings, ensure_ascii=False),
                match.state, match.implementation, match.created_at,
            ),
        )
        self._db.commit()
        return match

    def get_match(self, match_id: str) -> MatchAssessment:
        row = self._db.execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"match '{match_id}' not in SQLite store")
        return MatchAssessment(
            id=row["id"],
            candidate_profile_id=row["candidate_profile_id"],
            job_profile_id=row["job_profile_id"],
            score=row["score"],
            decision=row["decision"],
            strengths=json.loads(row["strengths"]) if row["strengths"] else [],
            gaps=json.loads(row["gaps"]) if row["gaps"] else [],
            learning_path=json.loads(row["learning_path"]) if row["learning_path"] else [],
            document_evidence=json.loads(row["document_evidence"]) if row["document_evidence"] else [],
            graph_evidence=json.loads(row["graph_evidence"]) if row["graph_evidence"] else [],
            details=json.loads(row["details"]) if "details" in row.keys() and row["details"] else {},
            summary=row["summary"] if "summary" in row.keys() and row["summary"] else "",
            warnings=json.loads(row["warnings"]) if "warnings" in row.keys() and row["warnings"] else [],
            state=row["state"],
            implementation=row["implementation"],
            created_at=row["created_at"],
        )

    # ── Recommendation cache ─────────────────────────────

    def get_recommendation(
        self,
        user_id: str,
        input_document_id: str,
        top_n: int,
        filters: str | None,
        max_per_company: int,
    ) -> dict | None:
        """Return a cached auto-match result or None.

        Returns ``{"result": dict, "created_at": str}`` on a hit.
        """
        row = self._db.execute(
            """SELECT result, created_at FROM recommendations
               WHERE user_id = ? AND input_document_id = ?
                 AND top_n = ? AND filters IS ? AND max_per_company = ?
               LIMIT 1""",
            (user_id, input_document_id, top_n, filters, max_per_company),
        ).fetchone()
        if row is None:
            return None
        try:
            return {"result": json.loads(row["result"]), "created_at": row["created_at"]}
        except (json.JSONDecodeError, TypeError):
            return None

    def save_recommendation(
        self,
        user_id: str,
        input_document_id: str,
        direction: str,
        top_n: int,
        filters: str | None,
        max_per_company: int,
        result: dict,
    ) -> dict:
        """Persist (or refresh) an auto-match result under its cache key."""
        from backend.app.domain.entities import resource_id, utc_now

        rec_id = resource_id("rec")
        now = utc_now()
        self._db.execute(
            """INSERT INTO recommendations
               (id, user_id, input_document_id, direction, top_n, filters,
                max_per_company, result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, input_document_id, top_n, filters, max_per_company)
               DO UPDATE SET result = excluded.result, created_at = excluded.created_at""",
            (
                rec_id, user_id, input_document_id, direction, top_n, filters,
                max_per_company, json.dumps(result, ensure_ascii=False), now,
            ),
        )
        self._db.commit()
        return {"result": result, "created_at": now}

    def list_recommendations(self, user_id: str, limit: int = 20) -> list[dict]:
        """Recent cached recommendations for a user (newest first)."""
        rows = self._db.execute(
            """SELECT id, input_document_id, direction, top_n, filters,
                      max_per_company, created_at
               FROM recommendations WHERE user_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def recover_stale_tasks(self, max_age_seconds: int = 300) -> int:
        """Mark profile tasks left running after a crashed/reloaded worker as failed."""
        now = datetime.now(timezone.utc)
        rows = self._db.execute(
            "SELECT id, updated_at FROM tasks WHERE status = ?", (TaskStatus.RUNNING.value,)
        ).fetchall()
        stale_ids: list[str] = []
        for row in rows:
            try:
                updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                stale_ids.append(row["id"])
                continue
            if (now - updated).total_seconds() >= max_age_seconds:
                stale_ids.append(row["id"])
        if not stale_ids:
            return 0
        stamp = _utc_now()
        self._db.executemany(
            "UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            [
                (TaskStatus.FAILED.value, "Profile generation was interrupted; please retry.", stamp, task_id)
                for task_id in stale_ids
            ],
        )
        self._db.commit()
        return len(stale_ids)

    def add_report(self, report: GeneratedReport) -> GeneratedReport:
        self._db.execute(
            """INSERT OR REPLACE INTO reports
               (id, match_id, language, sections, state, implementation, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                report.id, report.match_id, report.language,
                json.dumps(report.sections, ensure_ascii=False),
                report.state, report.implementation, report.created_at,
            ),
        )
        self._db.commit()
        return report

    # ── Health ────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        doc_count = self._db.table_count("documents")
        profile_count = self._db.table_count("profiles")
        user_count = self._db.table_count("users")
        return {
            "state": "available",
            "persistence": "sqlite",
            "resource_counts": {
                "documents": doc_count,
                "profiles": profile_count,
                "users": user_count,
            },
        }

    # ── Private helpers ──────────────────────────────────

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> SourceDocument:
        from backend.app.domain.entities import DocumentType

        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass

        source = {"source_system": row["source_system"]}
        if row["source_id"]:
            source["source_id"] = row["source_id"]

        return SourceDocument(
            id=row["id"],
            document_type=DocumentType(row["document_type"]),
            text=row["text"],
            source=source,
            metadata=metadata,
            created_at=row["created_at"],
            content_digest=row["content_digest"],
        )

    @staticmethod
    def _row_to_profile(row: ProfileRow) -> Profile:
        def _parse(raw: Optional[str], default: Any = None) -> Any:
            if not raw:
                return default if default is not None else []
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return default if default is not None else []

        return Profile(
            id=row.id,
            profile_type=ProfileType(row.profile_type),
            source_document_id=row.document_id,
            state=row.state,
            attributes=_parse(row.attributes, {}),
            evidence=_parse(row.evidence, []),
            warnings=_parse(row.warnings, []),
            implementation=row.implementation or "mock",
            created_at=row.created_at,
            artifacts=_parse(row.artifacts, {}),
        )


# Needed for type annotation in _row_to_document
import sqlite3  # noqa: E402
