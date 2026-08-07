"""Thread-safe, process-local resource repositories for contract testing."""

from __future__ import annotations

from threading import RLock
from typing import Optional

from backend.app.domain.entities import GeneratedReport, KnowledgeGraphSnapshot, MatchAssessment, Profile, ProfileType, SourceDocument, Task, TaskStatus
from backend.app.domain.errors import ResourceConflictError, ResourceNotFoundError


class InMemoryResourceRepository:
    """Volatile repository intentionally reset whenever the service restarts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._documents: dict[str, SourceDocument] = {}
        self._profiles: dict[str, Profile] = {}
        self._graphs: dict[str, KnowledgeGraphSnapshot] = {}
        self._matches: dict[str, MatchAssessment] = {}
        self._reports: dict[str, GeneratedReport] = {}
        self._tasks: dict[str, Task] = {}

    def add_document(self, document: SourceDocument) -> SourceDocument:
        with self._lock:
            self._documents[document.id] = document
        return document

    def get_document(self, document_id: str) -> SourceDocument:
        with self._lock:
            document = self._documents.get(document_id)
        if document is None:
            raise ResourceNotFoundError(f"document '{document_id}' was not found")
        return document

    def add_profile(self, profile: Profile) -> Profile:
        with self._lock:
            self._profiles[profile.id] = profile
        return profile

    def get_profile_by_document(self, document_id: str, profile_type: str) -> Optional[dict[str, Any]]:
        """Get profile by document_id and profile_type, return public dict or None."""
        with self._lock:
            for profile in self._profiles.values():
                if profile.source_document_id == document_id and profile.profile_type == profile_type:
                    return profile.public()
        return None

    def get_profile(self, profile_id: str, expected_type: Optional[ProfileType] = None) -> Profile:
        with self._lock:
            profile = self._profiles.get(profile_id)
        if profile is None:
            raise ResourceNotFoundError(f"profile '{profile_id}' was not found")
        if expected_type is not None and profile.profile_type is not expected_type:
            raise ResourceConflictError(
                f"profile '{profile_id}' is '{profile.profile_type.value}', expected '{expected_type.value}'"
            )
        return profile

    def add_graph(self, graph: KnowledgeGraphSnapshot) -> KnowledgeGraphSnapshot:
        with self._lock:
            self._graphs[graph.id] = graph
        return graph

    def get_graph(self, graph_id: str) -> KnowledgeGraphSnapshot:
        with self._lock:
            graph = self._graphs.get(graph_id)
        if graph is None:
            raise ResourceNotFoundError(f"knowledge graph '{graph_id}' was not found")
        return graph

    def add_match(self, match: MatchAssessment) -> MatchAssessment:
        with self._lock:
            self._matches[match.id] = match
        return match

    def get_match(self, match_id: str) -> MatchAssessment:
        with self._lock:
            match = self._matches.get(match_id)
        if match is None:
            raise ResourceNotFoundError(f"match '{match_id}' was not found")
        return match

    def add_report(self, report: GeneratedReport) -> GeneratedReport:
        with self._lock:
            self._reports[report.id] = report
        return report

    def add_task(self, task: Task) -> Task:
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise ResourceNotFoundError(f"task '{task_id}' was not found")
        return task

    def update_task(self, task_id: str, **fields: object) -> Task:
        from backend.app.domain.entities import utc_now

        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise ResourceNotFoundError(f"task '{task_id}' was not found")
            allowed = {"status", "profile_id", "error"}
            updates = {k: v for k, v in fields.items() if k in allowed}
            if "status" in updates and isinstance(updates["status"], TaskStatus):
                updates["status"] = updates["status"].value
            merged = {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status.value,
                "document_id": task.document_id,
                "profile_id": task.profile_id,
                "error": task.error,
                "created_at": task.created_at,
                "updated_at": utc_now(),
            }
            merged.update(updates)
            updated = Task(
                id=merged["id"],
                task_type=merged["task_type"],
                status=TaskStatus(merged["status"]),
                document_id=merged["document_id"],
                profile_id=merged["profile_id"],
                error=merged["error"],
                created_at=merged["created_at"],
                updated_at=merged["updated_at"],
            )
            self._tasks[task_id] = updated
        return updated

    def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": "available",
                "persistence": "memory",
                "resource_counts": {
                    "documents": len(self._documents),
                    "profiles": len(self._profiles),
                    "knowledge_graphs": len(self._graphs),
                    "matches": len(self._matches),
                    "reports": len(self._reports),
                },
            }
