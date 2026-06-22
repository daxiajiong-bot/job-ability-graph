"""Document resource endpoints; document text never appears in responses."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.v1.dependencies import get_facade
from backend.app.api.v1.errors import success
from backend.app.api.v1.schemas.common import SuccessEnvelope
from backend.app.api.v1.schemas.resources import DocumentCreateRequest
from backend.app.application.use_cases.contract_facade import ContractFacade


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=SuccessEnvelope, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreateRequest,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    document = facade.create_document(
        document_type=payload.document_type,
        text=payload.text,
        source=payload.source.model_dump(exclude_none=True),
        metadata=payload.metadata,
    )
    return success(request, {"document": document})


@router.get("/{document_id}", response_model=SuccessEnvelope)
def get_document(
    document_id: str,
    request: Request,
    facade: ContractFacade = Depends(get_facade),
) -> dict:
    return success(request, {"document": facade.get_document(document_id)})
