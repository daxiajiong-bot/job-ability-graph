"""FastAPI dependencies for the API edge."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, HTTPException, Request

from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.infrastructure.auth import decode_access_token


def get_facade(request: Request) -> ContractFacade:
    return request.app.state.container.facade


def get_repository(request: Request) -> Any:
    return request.app.state.container.repository


def get_current_user_id(x_user_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extract user ID from X-User-ID header."""
    return x_user_id


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extract current user info from Authorization: Bearer <token> header.

    Returns dict with ``user_id``, ``role``, ``username``.
    Falls back to X-User-ID header for backward compatibility.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = decode_access_token(token)
            return {
                "user_id": payload["sub"],
                "role": payload["role"],
                "username": payload["username"],
            }
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Fallback: anonymous user (backward compatibility)
    return {"user_id": None, "role": "job_seeker", "username": "anonymous"}
