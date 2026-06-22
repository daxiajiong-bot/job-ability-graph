"""Candidate and job profile resource endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.resources import ProfileCreateRequest
from backend.app.application.use_cases.contract_facade import ContractFacade


candidate_router = APIRouter(prefix="/candidate-profiles", tags=["Candidate profiles"])
job_router = APIRouter(prefix="/job-profiles", tags=["Job profiles"])


@candidate_router.post("", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_candidate_profile(
    payload: ProfileCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.create_candidate_profile(payload.document_id)})


@candidate_router.get("/{profile_id}", response_model=SuccessEnvelope)
def get_candidate_profile(
    profile_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.get_candidate_profile(profile_id)})


@job_router.post("", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_job_profile(
    payload: ProfileCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.create_job_profile(payload.document_id)})


@job_router.get("/{profile_id}", response_model=SuccessEnvelope)
def get_job_profile(
    profile_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.get_job_profile(profile_id)})
