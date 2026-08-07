from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from backend.app.domain.entities import MatchAssessment, Task, TaskStatus
from backend.app.infrastructure.sqlite.db import DatabaseManager
from backend.app.infrastructure.sqlite.repository import SQLiteResourceRepository


def test_match_details_round_trip_through_sqlite() -> None:
    with TemporaryDirectory() as tempdir:
        manager = DatabaseManager(Path(tempdir) / "app.db")
        repository = SQLiteResourceRepository(manager)
        match = MatchAssessment.create(
            "candidate-1",
            "job-1",
            {
                "state": "available",
                "implementation": "llm_matcher",
                "score": 72,
                "decision": "match",
                "details": {"skill_score": 80},
                "summary": "Useful match summary",
                "warnings": ["test warning"],
            },
        )

        repository.add_match(match)
        restored = repository.get_match(match.id)

        assert restored.details == {"skill_score": 80}
        assert restored.summary == "Useful match summary"
        assert restored.warnings == ["test warning"]
        manager.close()


def test_stale_running_tasks_are_recovered() -> None:
    with TemporaryDirectory() as tempdir:
        manager = DatabaseManager(Path(tempdir) / "app.db")
        repository = SQLiteResourceRepository(manager)
        task = repository.add_task(Task.create("create_candidate_profile", "document-1"))
        repository.update_task(task.id, status=TaskStatus.RUNNING)

        assert repository.recover_stale_tasks(max_age_seconds=0) == 1
        recovered = repository.get_task(task.id)
        assert recovered.status is TaskStatus.FAILED
        assert "interrupted" in (recovered.error or "")
        manager.close()
