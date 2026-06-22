"""Domain errors that the HTTP layer maps to stable API errors."""

from __future__ import annotations

from typing import Any, Optional


class DomainError(Exception):
    code = "domain_error"
    status_code = 400

    def __init__(self, message: str, details: Optional[list[dict[str, Any]]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class ResourceNotFoundError(DomainError):
    code = "resource_not_found"
    status_code = 404


class ResourceConflictError(DomainError):
    code = "resource_conflict"
    status_code = 409
