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


class InvalidInputError(DomainError):
    code = "invalid_input"
    status_code = 400


class UnsupportedMediaTypeError(DomainError):
    code = "unsupported_media_type"
    status_code = 415


class PayloadTooLargeError(DomainError):
    code = "payload_too_large"
    status_code = 413


class OcrProcessingError(DomainError):
    code = "ocr_processing_error"
    status_code = 422


class OcrUnavailableError(DomainError):
    code = "ocr_unavailable"
    status_code = 503


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    status_code = 403
