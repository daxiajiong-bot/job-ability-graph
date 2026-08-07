"""Shared formal API envelope schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    request_id: str
    api_version: str = "v1"
    implementation: str = "mock"
    persistence: str = "memory"


class SuccessEnvelope(BaseModel):
    data: dict[str, Any]
    meta: ResponseMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    meta: ResponseMeta
