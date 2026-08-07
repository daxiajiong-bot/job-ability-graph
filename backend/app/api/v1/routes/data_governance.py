"""Data governance endpoints for traceable graph RAG inputs."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.governance import (
    GovernanceProcessRequest,
    GovernanceRegisterPathRequest,
    GovernanceRetrievalRequest,
)
from backend.app.application.use_cases.contract_facade import ContractFacade
from backend.app.domain.entities import DocumentType
from backend.app.domain.errors import InvalidInputError


router = APIRouter(prefix="/data-governance", tags=["Data governance"])


@router.post("/documents/register", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
async def register_governed_upload(
    request: Request,
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    source_system: str = Form(default="upload"),
    external_id: Optional[str] = Form(default=None),
    uri: Optional[str] = Form(default=None),
    published_at: Optional[str] = Form(default=None),
    metadata_json: Optional[str] = Form(default=None),
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    content = await file.read()
    result = facade.register_governance_file(
        document_type=document_type,
        content=content,
        file_name=file.filename or "upload.txt",
        mime_type=file.content_type,
        source=_source(source_system, external_id, uri, published_at),
        metadata=_metadata(metadata_json),
    )
    return success(request, result)


@router.post("/documents/register-path", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def register_governed_path(
    payload: GovernanceRegisterPathRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.register_governance_path(
        document_type=payload.document_type,
        path=payload.path,
        source=_source(payload.source_system, payload.external_id, payload.uri, payload.published_at),
        metadata=payload.metadata,
    )
    return success(request, result)


@router.post("/documents/{doc_id}/process", response_model=SuccessEnvelope)
def process_governed_document(
    doc_id: str,
    payload: GovernanceProcessRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"processing": facade.process_governance_document(doc_id, payload.version)})


@router.get("/documents/{doc_id}", response_model=SuccessEnvelope)
def get_governed_document(
    doc_id: str,
    request: Request,
    version: Optional[int] = None,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"governed_document": facade.get_governance_document(doc_id, version)})


@router.get("/documents/{doc_id}/lineage", response_model=SuccessEnvelope)
def get_governed_lineage(
    doc_id: str,
    request: Request,
    version: Optional[int] = None,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"lineage": facade.get_governance_lineage(doc_id, version)})


@router.post("/rag/search", response_model=SuccessEnvelope)
def search_governed_chunks(
    payload: GovernanceRetrievalRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.search_governance_rag(payload.query, payload.doc_ids, payload.top_k)
    return success(request, {"retrieval": result})


@router.post("/rag/answer", response_model=SuccessEnvelope)
def answer_from_governed_chunks(
    payload: GovernanceRetrievalRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    result = facade.answer_governance_rag(payload.query, payload.doc_ids, payload.top_k)
    return success(request, {"answer": result})


def _metadata(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InvalidInputError("metadata_json must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise InvalidInputError("metadata_json must decode to a JSON object")
    return parsed


def _source(
    source_system: str,
    external_id: Optional[str],
    uri: Optional[str],
    published_at: Optional[str],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "source_system": source_system.strip() or "upload",
            "external_id": external_id,
            "uri": uri,
            "published_at": published_at,
        }.items()
        if value is not None
    }
