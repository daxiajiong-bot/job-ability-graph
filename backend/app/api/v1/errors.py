"""Uniform envelopes and exception mapping for v3."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.domain.errors import DomainError


def _meta(request: Request) -> dict[str, str]:
    return {
        "request_id": getattr(request.state, "request_id", "unknown"),
        "api_version": "v1",
        "implementation": "mock",
        "persistence": "memory",
    }


def success(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "meta": _meta(request)}


def _error(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Optional[list[dict[str, Any]]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details or []},
            "meta": _meta(request),
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _error(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": [str(part) for part in error["loc"]], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return _error(request, 422, "validation_error", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = str(exc.detail) if exc.detail else "HTTP error"
        return _error(request, exc.status_code, f"http_{exc.status_code}", message)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error(request, 500, "internal_error", "Unexpected server error")
