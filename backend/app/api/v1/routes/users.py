"""User management and user-scoped document endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, status

from backend.app.api.v1.dependencies import get_facade, get_repository
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.infrastructure.sqlite.repository import SQLiteResourceRepository


router = APIRouter(prefix="/users", tags=["Users"])


def _get_user_id(x_user_id: Optional[str] = Header(default=None)) -> Optional[str]:
    return x_user_id


@router.post("/init", response_model=SuccessEnvelope, status_code=status.HTTP_200_OK)
def init_user(
    request: Request,
    user_id: Optional[str] = Depends(_get_user_id),
) -> dict:
    """Initialize a user session. Creates user record if not exists."""
    repository = get_repository(request)
    if not isinstance(repository, SQLiteResourceRepository):
        return success(request, {"user_id": user_id or "anonymous", "persistence": "memory"})

    if not user_id:
        from uuid import uuid4
        user_id = uuid4().hex

    repository.ensure_user(user_id)
    counts = repository.get_user_document_count(user_id)
    return success(request, {
        "user_id": user_id,
        "persistence": "sqlite",
        "counts": counts,
    })


@router.get("/{user_id}/documents", response_model=SuccessEnvelope)
def list_user_documents(
    user_id: str,
    request: Request,
    document_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """List documents visible to a user (system JDs + own uploads)."""
    repository = get_repository(request)
    if not isinstance(repository, SQLiteResourceRepository):
        return success(request, {"items": [], "total": 0})

    repository.ensure_user(user_id)
    result = repository.list_documents(
        user_id=user_id,
        document_type=document_type,
        offset=offset,
        limit=limit,
    )
    return success(request, result)
