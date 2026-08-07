"""FastAPI dependencies for the API edge."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, Request

from backend.app.application.use_cases.contract_facade import ContractFacade


def get_facade(request: Request) -> ContractFacade:
    return request.app.state.container.facade


def get_repository(request: Request) -> Any:
    return request.app.state.container.repository


def get_current_user_id(x_user_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extract user ID from X-User-ID header."""
    return x_user_id
