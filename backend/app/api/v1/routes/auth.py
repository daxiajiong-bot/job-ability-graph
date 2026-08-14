"""Authentication endpoints: register, login, get current user."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field

from backend.app.api.v1.errors import _error, success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.infrastructure.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.infrastructure.sqlite.repository import SQLiteResourceRepository


router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request / Response schemas ─────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_一-鿿]+$")
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="job_seeker", pattern=r"^(job_seeker|hr)$")
    display_name: Optional[str] = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


# ── Endpoints ──────────────────────────────────────────────

@router.post("/register", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request) -> dict:
    """Register a new user."""
    repository = _get_repository(request)

    # Check if username already exists
    existing = repository.get_user_by_username(body.username)
    if existing:
        return _error(request, 409, "username_taken", f"用户名 '{body.username}' 已被注册")

    from uuid import uuid4

    user_id = f"u_{uuid4().hex}"
    password_hash = hash_password(body.password)
    display_name = body.display_name or body.username

    user = repository.create_user(
        user_id=user_id,
        username=body.username,
        password_hash=password_hash,
        role=body.role,
        display_name=display_name,
    )

    token = create_access_token(user_id, body.role, body.username)

    return success(request, {
        "token": token,
        "user": {
            "user_id": user_id,
            "username": body.username,
            "role": body.role,
            "display_name": display_name,
        },
    })


@router.post("/login", response_model=SuccessEnvelope, status_code=status.HTTP_200_OK)
def login(body: LoginRequest, request: Request) -> dict:
    """Login with username and password."""
    repository = _get_repository(request)

    user = repository.get_user_by_username(body.username)
    if not user:
        return _error(request, 401, "invalid_credentials", "用户名或密码错误")

    if not verify_password(body.password, user["password_hash"]):
        return _error(request, 401, "invalid_credentials", "用户名或密码错误")

    # Update last_active_at
    repository.ensure_user(user["user_id"])

    token = create_access_token(user["user_id"], user["role"], user["username"])

    return success(request, {
        "token": token,
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
        },
    })


@router.get("/me", response_model=SuccessEnvelope, status_code=status.HTTP_200_OK)
def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Get current user info from JWT token."""
    repository = _get_repository(request)

    user_info = _extract_user(authorization, request)
    if isinstance(user_info, dict) and "error" in user_info:
        return user_info

    user = repository.get_user_by_id(user_info["user_id"])
    if not user:
        return _error(request, 404, "user_not_found", "用户不存在")

    return success(request, {"user": user})


# ── Helpers ────────────────────────────────────────────────

def _get_repository(request: Request):
    return request.app.state.container.repository


def _extract_user(authorization: Optional[str], request: Request) -> dict:
    """Extract user info from Authorization header. Returns user dict or error response."""
    if not authorization or not authorization.startswith("Bearer "):
        return _error(request, 401, "not_authenticated", "请先登录")

    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        return _error(request, 401, "invalid_token", str(e))

    return {
        "user_id": payload["sub"],
        "role": payload["role"],
        "username": payload["username"],
    }
