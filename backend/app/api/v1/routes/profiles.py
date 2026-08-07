"""Candidate and job profile resource endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.resources import ProfileCreateRequest
from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.domain.entities import TaskStatus


class BatchProfileRequest(BaseModel):
    document_ids: List[str] = Field(min_length=1, max_length=200)


candidate_router = APIRouter(prefix="/candidate-profiles", tags=["Candidate profiles"])
job_router = APIRouter(prefix="/job-profiles", tags=["Job profiles"])


# ── Async profile creation (returns task_id immediately) ──


@candidate_router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_candidate_profile(
    payload: ProfileCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    task = facade.start_create_candidate_profile(payload.document_id)
    background_tasks.add_task(facade.execute_profile_task, task.id)
    return {"data": {"task": task.public()}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


@candidate_router.get("/tasks/{task_id}")
def get_candidate_profile_task(
    task_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    task = facade.get_task(task_id)
    result = task.public()
    if task.status == TaskStatus.SUCCEEDED and task.profile_id:
        result["profile"] = facade.get_candidate_profile(task.profile_id)
    return {"data": {"task": result}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


@job_router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_job_profile(
    payload: ProfileCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    task = facade.start_create_job_profile(payload.document_id)
    background_tasks.add_task(facade.execute_profile_task, task.id)
    return {"data": {"task": task.public()}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


@job_router.get("/tasks/{task_id}")
def get_job_profile_task(
    task_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    task = facade.get_task(task_id)
    result = task.public()
    if task.status == TaskStatus.SUCCEEDED and task.profile_id:
        result["profile"] = facade.get_job_profile(task.profile_id)
    return {"data": {"task": result}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


# ── Sync profile retrieval (by profile_id) ──


@candidate_router.post("/by-documents")
def get_candidate_profiles_by_documents(
    payload: BatchProfileRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    profiles = facade.get_candidate_profiles_by_documents(payload.document_ids)
    return {"data": {"profiles": profiles}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


@job_router.post("/by-documents")
def get_job_profiles_by_documents(
    payload: BatchProfileRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    profiles = facade.get_job_profiles_by_documents(payload.document_ids)
    return {"data": {"profiles": profiles}, "meta": {"request_id": getattr(request.state, "request_id", None)}}


@candidate_router.get("/{profile_id}", response_model=SuccessEnvelope)
def get_candidate_profile(
    profile_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.get_candidate_profile(profile_id)})


@job_router.get("/{profile_id}", response_model=SuccessEnvelope)
def get_job_profile(
    profile_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"profile": facade.get_job_profile(profile_id)})
