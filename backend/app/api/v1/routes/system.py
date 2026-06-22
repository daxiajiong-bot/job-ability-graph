"""Capability introspection endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.application.use_cases.contract_facade import ContractFacade


router = APIRouter(tags=["System"])


@router.get("/capabilities", response_model=SuccessEnvelope)
def capabilities(request: Request, facade: ContractFacade = Depends(get_facade)) -> dict:
    return success(request, facade.capabilities())
